"""Resolução dos municípios-alvo pela API de Localidades do IBGE.

Os códigos IBGE não são fixados na configuração de propósito: um código errado
digitado à mão produz uma base silenciosamente incompleta — o município
simplesmente não aparece, e nada acusa o erro. Aqui eles são derivados do nome
da região imediata, e o resultado fica versionado em ``dados/municipios.json``
para que a coleta continue funcionando se o IBGE estiver fora do ar.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import DADOS, fontes, municipios as cfg_municipios
from .http import Cliente
from .texto import normalizar

log = logging.getLogger("licita.ibge")

ARQUIVO = DADOS / "municipios.json"


@dataclass(frozen=True)
class Municipio:
    codigo_ibge: str
    nome: str
    uf: str
    regiao_imediata: str
    regiao_intermediaria: str
    motivo_inclusao: str      # "regiao_imediata" ou "extra"
    prioritario: bool

    @property
    def rotulo(self) -> str:
        return f"{self.nome}/{self.uf}"


def _extrair_regioes(bruto: dict) -> tuple[str, str]:
    """Lê região imediata e intermediária, tolerando variação de chave.

    A API usa ``regiao-imediata`` (com hífen); implementações e versões antigas
    já usaram ``regiaoImediata``. Ausência não é erro fatal — o município ainda
    pode entrar pela lista de extras.
    """
    imediata = bruto.get("regiao-imediata") or bruto.get("regiaoImediata") or {}
    nome_imediata = imediata.get("nome", "")
    intermediaria = (
        imediata.get("regiao-intermediaria")
        or imediata.get("regiaoIntermediaria")
        or {}
    )
    return nome_imediata, intermediaria.get("nome", "")


def _uf_do_municipio(bruto: dict, imediata: dict | None = None) -> str:
    """A sigla da UF aparece aninhada em caminhos diferentes conforme a versão."""
    caminhos = [
        ("microrregiao", "mesorregiao", "UF"),
        ("regiao-imediata", "regiao-intermediaria", "UF"),
    ]
    for caminho in caminhos:
        no = bruto
        for chave in caminho:
            no = (no or {}).get(chave) if isinstance(no, dict) else None
        if isinstance(no, dict) and no.get("sigla"):
            return no["sigla"]
    return cfg_municipios().get("uf", "")


def resolver(cliente: Cliente | None = None, forcar: bool = False) -> list[Municipio]:
    """Devolve os municípios-alvo, consultando o IBGE ou o arquivo versionado."""
    if not forcar:
        salvos = carregar_salvos()
        if salvos:
            return salvos

    cliente = cliente or Cliente()
    cfg = cfg_municipios()
    f = fontes()["ibge"]
    url = f["base"] + f["municipios_por_uf"].format(uf=cfg["codigo_uf_ibge"])

    resp = cliente.obter(url)
    if not resp.ok or not isinstance(resp.dados, list):
        salvos = carregar_salvos()
        if salvos:
            log.warning("IBGE indisponível (%s); usando %s", resp.erro or resp.status, ARQUIVO)
            return salvos
        raise RuntimeError(
            f"não foi possível resolver municípios pelo IBGE ({resp.erro or resp.status}) "
            f"e não há {ARQUIVO} para usar como alternativa"
        )

    alvos_regiao = {normalizar(r) for r in cfg.get("regioes_imediatas", [])}
    alvos_extra = {normalizar(m) for m in cfg.get("municipios_extras", [])}
    prioritarios = {normalizar(m) for m in cfg.get("prioritarios", [])}

    encontrados: list[Municipio] = []
    extras_vistos: set[str] = set()

    for bruto in resp.dados:
        nome = bruto.get("nome", "")
        nome_norm = normalizar(nome)
        imediata, intermediaria = _extrair_regioes(bruto)

        por_regiao = normalizar(imediata) in alvos_regiao
        por_extra = nome_norm in alvos_extra
        if not (por_regiao or por_extra):
            continue
        if por_extra:
            extras_vistos.add(nome_norm)

        encontrados.append(
            Municipio(
                codigo_ibge=str(bruto.get("id", "")),
                nome=nome,
                uf=_uf_do_municipio(bruto),
                regiao_imediata=imediata,
                regiao_intermediaria=intermediaria,
                motivo_inclusao="regiao_imediata" if por_regiao else "extra",
                prioritario=nome_norm in prioritarios,
            )
        )

    faltando = alvos_extra - extras_vistos
    if faltando:
        log.warning("municípios extras não encontrados na UF: %s", sorted(faltando))

    regioes_vistas = {normalizar(m.regiao_imediata) for m in encontrados}
    for alvo in sorted(alvos_regiao - regioes_vistas):
        log.warning("região imediata sem municípios correspondentes: %r", alvo)

    encontrados.sort(key=lambda m: (not m.prioritario, normalizar(m.nome)))
    salvar(encontrados)
    return encontrados


def salvar(lista: list[Municipio]) -> None:
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    with ARQUIVO.open("w", encoding="utf-8") as fh:
        json.dump([asdict(m) for m in lista], fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def carregar_salvos(caminho: Path = ARQUIVO) -> list[Municipio]:
    if not caminho.exists():
        return []
    try:
        with caminho.open(encoding="utf-8") as fh:
            return [Municipio(**r) for r in json.load(fh)]
    except (json.JSONDecodeError, TypeError, OSError) as exc:
        log.warning("%s ilegível (%s); será refeito pelo IBGE", caminho, exc)
        return []
