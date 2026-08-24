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
        self.pausa = cfg["pausa_entre_chamadas_s"]
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
        if decorrido < self.pausa:
            time.sleep(self.pausa - decorrido)
        self._ultimo_envio = time.monotonic()

    def _espera(self, tentativa: int, retry_after: str | None) -> float:
        """Backoff exponencial com jitter; honra Retry-After quando presente."""
        if retry_after:
            try:
                return min(float(retry_after), self.backoff_teto)
            except ValueError:
                pass
        bruto = self.backoff_base * (2 ** (tentativa - 1))
        return min(bruto, self.backoff_teto) * random.uniform(0.7, 1.3)

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

            if resp.status_code in STATUS_RETENTAVEIS and tentativa < self.max_tentativas:
                ultimo_erro = f"HTTP {resp.status_code}"
                time.sleep(self._espera(tentativa, resp.headers.get("Retry-After")))
                continue

            duracao = time.monotonic() - inicio

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

    def paginar(self, url: str, params: dict, limite_paginas: int = 200):
        """Itera páginas de um endpoint paginado do PNCP.

        Encerra ao ver página vazia, ao atingir ``totalPaginas`` ou ao receber erro.
        Devolve tuplas ``(registros, resposta)`` para que quem chama possa registrar
        falhas parciais sem perder o que já foi coletado.
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
            pagina += 1
