"""Camada HTTP resiliente.

Princípio de projeto: nada aqui levanta exceção por falha de rede ou por status
HTTP de erro. Toda chamada devolve uma ``Resposta``, e quem chama decide o que
fazer. Isso existe porque a coleta varre dezenas de municípios × modalidades ×
janelas: um 500 isolado em um município não pode derrubar a execução inteira.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from .config import CACHE, fontes

log = logging.getLogger("licita.http")

# Status que valem nova tentativa: throttling e falhas transitórias de servidor.
STATUS_RETENTAVEIS = {408, 425, 429, 500, 502, 503, 504}

# Excesso de requisições. Tratado à parte dos 5xx porque a resposta certa é
# diferente: um 500 é transitório e some sozinho, um 429 só some se quem chama
# desacelerar. A varredura de 24/08 tomou 103 destes seguindo no mesmo ritmo.
STATUS_EXCESSO = 429


@dataclass
class Resposta:
    """Resultado de uma chamada HTTP, com sucesso ou não."""

    url: str
    status: int | None
    dados: Any = None
    erro: str | None = None
    do_cache: bool = False
    tentativas: int = 1
    duracao_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.erro is None and self.status is not None and 200 <= self.status < 300

    @property
    def vazio(self) -> bool:
        """204, ou 200 com corpo vazio. O PNCP usa 204 para 'nada no período'."""
        if self.status == 204:
            return True
        if not self.ok:
            return False
        if self.dados is None:
            return True
        if isinstance(self.dados, dict):
            return bool(self.dados.get("empty")) or not self.dados.get("data")
        if isinstance(self.dados, list):
            return not self.dados
        return False


@dataclass
class Cliente:
    """Sessão HTTP com retry exponencial, rate limit e cache em disco."""

    usar_cache: bool = True
    perfil: str = "http"          # seção de config: "http" ou "http_massa"
    _sessao: requests.Session = field(default_factory=requests.Session, repr=False)
    _ultimo_envio: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        cfg = fontes()[self.perfil]
        self.timeout = cfg["timeout_s"]
        self.max_tentativas = cfg["max_tentativas"]
        self.backoff_base = cfg["backoff_base_s"]
        self.backoff_teto = cfg["backoff_teto_s"]
        # Retry-After é instrução do servidor (RFC 9110 §10.2.3), não sugestão:
        # tem teto próprio, mais alto que o do backoff calculado. Truncá-lo no
        # teto do backoff fazia esperar 10s quando o PNCP pedia mais, e o 429
        # voltava na requisição seguinte.
        self.retry_after_teto = cfg.get("retry_after_teto_s", 120.0)
        self.pausa = cfg["pausa_entre_chamadas_s"]
        self.pausa_teto = cfg.get("pausa_teto_s", 8.0)
        self.sucessos_para_afrouxar = cfg.get("sucessos_para_afrouxar", 20)
        # Ritmo corrente. Sobe a cada 429 e desce sozinho depois de uma sequência
        # de sucessos: o valor de config é o piso, não o ritmo fixo.
        self._pausa_atual = self.pausa
        self._sucessos_seguidos = 0
        self.excessos = 0            # quantos 429 esta sessão levou
        self.cache_ttl_s = cfg["cache_ttl_h"] * 3600
        self._sessao.headers.update(
            {"User-Agent": cfg["user_agent"], "Accept": "application/json"}
        )

    # ------------------------------------------------------------------ cache

    def _caminho_cache(self, url: str, params: dict | None) -> Path:
        chave = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(chave.encode("utf-8")).hexdigest()[:32]
        return CACHE / digest[:2] / f"{digest}.json"

    def _ler_cache(self, caminho: Path) -> Any | None:
        if not self.usar_cache or not caminho.exists():
            return None
        if time.time() - caminho.stat().st_mtime > self.cache_ttl_s:
            return None
        try:
            with caminho.open(encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return None  # cache corrompido é o mesmo que cache ausente

    def _gravar_cache(self, caminho: Path, dados: Any) -> None:
        if not self.usar_cache:
            return
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            with caminho.open("w", encoding="utf-8") as fh:
                json.dump(dados, fh, ensure_ascii=False)
        except OSError as exc:
            log.debug("falha ao gravar cache %s: %s", caminho, exc)

    # ------------------------------------------------------------------ envio

    def _respeitar_rate_limit(self) -> None:
        decorrido = time.monotonic() - self._ultimo_envio
        if decorrido < self._pausa_atual:
            time.sleep(self._pausa_atual - decorrido)
        self._ultimo_envio = time.monotonic()

    def _frear(self) -> None:
        """Dobra a pausa entre chamadas depois de um 429, até o teto.

        Sem isto, esperar e repetir resolve a requisição atual e não muda nada
        para as seguintes: a varredura volta ao ritmo que causou o bloqueio e
        toma 429 de novo. O freio precisa valer para a sessão inteira.
        """
        self.excessos += 1
        self._sucessos_seguidos = 0
        anterior = self._pausa_atual
        self._pausa_atual = min(max(self._pausa_atual * 2, 0.5), self.pausa_teto)
        if self._pausa_atual > anterior:
            log.warning("HTTP 429: pausa entre chamadas %.2fs -> %.2fs",
                        anterior, self._pausa_atual)

    def _afrouxar(self) -> None:
        """Alivia o freio depois de uma sequência de sucessos, sem voltar abaixo
        da pausa de config, que é o piso."""
        if self._pausa_atual <= self.pausa:
            return
        self._sucessos_seguidos += 1
        if self._sucessos_seguidos < self.sucessos_para_afrouxar:
            return
        self._sucessos_seguidos = 0
        self._pausa_atual = max(self.pausa, self._pausa_atual * 0.8)
        log.info("ritmo normalizando: pausa entre chamadas -> %.2fs", self._pausa_atual)

    def _espera(self, tentativa: int, retry_after: str | None,
                status: int | None = None) -> float:
        """Backoff exponencial com jitter; honra Retry-After quando presente."""
        if retry_after:
            try:
                return min(float(retry_after), self.retry_after_teto)
            except ValueError:
                pass
        bruto = self.backoff_base * (2 ** (tentativa - 1))
        teto = self.backoff_teto
        if status == STATUS_EXCESSO:
            # Excesso de requisições pede espera mais longa que uma falha de
            # servidor: o teto do backoff comum é curto demais para o bloqueio
            # sair. O limite é o mesmo do Retry-After.
            bruto *= 4
            teto = self.retry_after_teto
        return min(bruto, teto) * random.uniform(0.7, 1.3)

    def obter(self, url: str, params: dict | None = None) -> Resposta:
        """GET com retry. Devolve ``Resposta`` mesmo em falha total."""
        caminho = self._caminho_cache(url, params)
        em_cache = self._ler_cache(caminho)
        if em_cache is not None:
            return Resposta(url=url, status=200, dados=em_cache, do_cache=True)

        inicio = time.monotonic()
        ultimo_erro = "sem tentativa realizada"

        for tentativa in range(1, self.max_tentativas + 1):
            self._respeitar_rate_limit()
            try:
                resp = self._sessao.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                ultimo_erro = f"{type(exc).__name__}: {exc}"
                if tentativa < self.max_tentativas:
                    time.sleep(self._espera(tentativa, None))
                    continue
                break

            if resp.status_code == STATUS_EXCESSO:
                # Freia sempre, inclusive na última tentativa: o próximo GET
                # desta sessão já sai no ritmo mais lento.
                self._frear()

            if resp.status_code in STATUS_RETENTAVEIS and tentativa < self.max_tentativas:
                ultimo_erro = f"HTTP {resp.status_code}"
                time.sleep(self._espera(tentativa, resp.headers.get("Retry-After"),
                                        resp.status_code))
                continue

            duracao = time.monotonic() - inicio

            if resp.ok:
                self._afrouxar()

            if resp.status_code == 204 or not resp.content:
                return Resposta(url=resp.url, status=resp.status_code, dados=None,
                                tentativas=tentativa, duracao_s=duracao)

            if not resp.ok:
                return Resposta(url=resp.url, status=resp.status_code,
                                erro=f"HTTP {resp.status_code}: {resp.text[:300]}",
                                tentativas=tentativa, duracao_s=duracao)

            try:
                dados = resp.json()
            except ValueError:
                return Resposta(url=resp.url, status=resp.status_code,
                                erro=f"resposta não-JSON: {resp.text[:200]}",
                                tentativas=tentativa, duracao_s=duracao)

            self._gravar_cache(caminho, dados)
            return Resposta(url=resp.url, status=resp.status_code, dados=dados,
                            tentativas=tentativa, duracao_s=duracao)

        return Resposta(url=url, status=None, erro=ultimo_erro,
                        tentativas=self.max_tentativas,
                        duracao_s=time.monotonic() - inicio)

    def obter_bruto(self, url: str, params: dict | None = None) -> Resposta:
        """GET sem exigir JSON. Devolve tipo de conteúdo, tamanho e um trecho.

        Existe para sondar fonte que não é API JSON — a spec YAML do AUDESP, a
        página de conjuntos de dados do TCE-SP. Pela via normal elas voltariam
        como "resposta não-JSON", que é veredito sobre o formato e não sobre a
        existência da fonte. Não usa cache: sonda tem de bater na origem.
        """
        inicio = time.monotonic()
        self._respeitar_rate_limit()
        try:
            resp = self._sessao.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            return Resposta(url=url, status=None, erro=f"{type(exc).__name__}: {exc}",
                            duracao_s=time.monotonic() - inicio)
        if resp.status_code == STATUS_EXCESSO:
            self._frear()
        texto = resp.text or ""
        return Resposta(
            url=resp.url, status=resp.status_code,
            dados={
                "tipo_conteudo": resp.headers.get("Content-Type", ""),
                "bytes": len(resp.content or b""),
                "trecho": texto[:600],
            },
            erro=None if resp.ok else f"HTTP {resp.status_code}",
            duracao_s=time.monotonic() - inicio,
        )

    def paginar(self, url: str, params: dict, limite_paginas: int = 200):
        """Itera páginas de um endpoint paginado do PNCP.

        Dois formatos de corpo convivem nas rotas do PNCP: a API de consulta
        envelopa em ``{"data": [...], "totalPaginas": N, ...}``; a API de
        detalhe (``/itens``, por exemplo) devolve a lista crua, sem envelope
        e sem contagem de páginas. Para o envelope, a parada usa
        ``totalPaginas``/``paginasRestantes``. Para lista crua, não há como
        saber o total de antemão — a parada é por página vazia ou por página
        mais curta que o ``tamanhoPagina`` pedido, sinal de que é a última.

        Encerra ao ver página vazia, ao atingir o fim conhecido ou ao receber
        erro. Devolve tuplas ``(registros, resposta)`` para que quem chama
        possa registrar falhas parciais sem perder o que já foi coletado.
        """
        pagina = 1
        while pagina <= limite_paginas:
            atual = dict(params, pagina=pagina)
            resp = self.obter(url, atual)

            if not resp.ok:
                yield [], resp
                return
            if resp.vazio:
                return

            corpo = resp.dados
            registros = corpo.get("data", []) if isinstance(corpo, dict) else corpo
            if not registros:
                return

            yield registros, resp

            if isinstance(corpo, dict):
                total = corpo.get("totalPaginas")
                if isinstance(total, int) and pagina >= total:
                    return
                if corpo.get("paginasRestantes") == 0:
                    return
            else:
                tamanho_pedido = atual.get("tamanhoPagina")
                if isinstance(tamanho_pedido, int) and len(registros) < tamanho_pedido:
                    return
            pagina += 1
