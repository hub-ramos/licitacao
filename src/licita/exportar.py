"""Exports CSV/XLSX e geração do painel HTML.

Compromisso de estabilidade de esquema: coluna nova é sempre acrescentada ao
final; coluna existente nunca é removida nem renomeada. Os CSV alimentam
relatórios de BI externos, e coluna que desaparece quebra relatório sem avisar.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .config import DADOS, RAIZ
from .config import glossario as _glossario
from .db import Base

log = logging.getLogger("licita.exportar")

TEMPLATE = RAIZ / "painel" / "template.html"
PAINEL = DADOS / "painel.html"
MARCADOR = "/*__DADOS__*/null"

# Consultas exportadas. A ordem das colunas do SELECT é o contrato do export.
EXPORTS: dict[str, str] = {
    "itens": "SELECT * FROM v_item_completo ORDER BY ano DESC, municipio, numero_controle_pncp, numero_item",
    "radar": "SELECT * FROM v_radar ORDER BY date(substr(data_encerramento_proposta,1,10))",
    "vencedores": "SELECT * FROM v_vencedor ORDER BY ano DESC, mes DESC, nome_fornecedor",
    "metricas": """
        SELECT m.*, mu.nome AS municipio
          FROM metrica_mun_seg_ano m
          LEFT JOIN municipio mu ON mu.codigo_ibge = m.codigo_ibge
         ORDER BY m.indice_oportunidade DESC NULLS LAST, m.valor_estimado DESC
    """,
    "cobertura": """
        SELECT c.*, mu.nome AS municipio
          FROM cobertura c
          LEFT JOIN municipio mu ON mu.codigo_ibge = c.codigo_ibge
         ORDER BY mu.nome, c.ano DESC, c.modalidade_id
    """,
    "contratos": "SELECT * FROM contrato ORDER BY data_publicacao DESC",
    "atas": "SELECT * FROM ata ORDER BY vigencia_fim DESC",
    "municipios": "SELECT * FROM municipio ORDER BY prioritario DESC, nome",
    "falhas_coleta": "SELECT * FROM coleta_log ORDER BY id DESC LIMIT 2000",
}

# Quanto do painel vai embutido no HTML. Acima disso o arquivo fica pesado demais
# para abrir no celular, que é o uso principal do painel.
LIMITE_PAINEL = {"itens": 8000, "radar": 1000, "metricas": 3000, "vencedores": 8000}


def _linhas(base: Base, sql: str) -> tuple[list[str], list[list[Any]]]:
    cursor = base.con.execute(sql)
    colunas = [d[0] for d in cursor.description]
    return colunas, [list(linha) for linha in cursor]


def para_csv(base: Base, destino: Path = DADOS) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    escritos: list[Path] = []
    for nome, sql in EXPORTS.items():
        colunas, linhas = _linhas(base, sql)
        caminho = destino / f"{nome}.csv"
        with caminho.open("w", encoding="utf-8-sig", newline="") as fh:
            escritor = csv.writer(fh, delimiter=";")   # ; abre direto no Excel pt-BR
            escritor.writerow(colunas)
            escritor.writerows(linhas)
        escritos.append(caminho)
        log.info("export %s: %d linhas", caminho.name, len(linhas))
    return escritos


def para_xlsx(base: Base, destino: Path = DADOS / "licitacoes.xlsx") -> Path | None:
    try:
        from openpyxl import Workbook
    except ImportError:
        log.warning("openpyxl ausente; export XLSX ignorado")
        return None

    livro = Workbook()
    livro.remove(livro.active)
    for nome, sql in EXPORTS.items():
        colunas, linhas = _linhas(base, sql)
        aba = livro.create_sheet(nome[:31])
        aba.append(colunas)
        for linha in linhas:
            aba.append(linha)
        aba.freeze_panes = "A2"
        if linhas:
            aba.auto_filter.ref = aba.dimensions
    destino.parent.mkdir(parents=True, exist_ok=True)
    livro.save(destino)
    log.info("export %s", destino.name)
    return destino


def _dicionarios(base: Base, sql: str, limite: int | None = None) -> list[dict]:
    colunas, linhas = _linhas(base, sql)
    if limite is not None:
        linhas = linhas[:limite]
    return [dict(zip(colunas, linha)) for linha in linhas]


def para_painel(base: Base, destino: Path = PAINEL) -> Path:
    """Gera o painel HTML com os dados embutidos, sem dependência externa."""
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"template do painel ausente: {TEMPLATE}")

    dados = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "itens": _dicionarios(base, EXPORTS["itens"], LIMITE_PAINEL["itens"]),
        "radar": _dicionarios(base, EXPORTS["radar"], LIMITE_PAINEL["radar"]),
        "metricas": _dicionarios(base, EXPORTS["metricas"], LIMITE_PAINEL["metricas"]),
        "vencedores": _dicionarios(base, EXPORTS["vencedores"], LIMITE_PAINEL["vencedores"]),
        "glossario": _glossario(),
        "totais": {
            "contratacoes": base.contar("contratacao"),
            "itens": base.contar("item"),
            "municipios": base.contar("municipio"),
            "fornecedores": base.contar("fornecedor"),
        },
    }

    bruto = json.dumps(dados, ensure_ascii=False, default=str)
    # </script> dentro do JSON encerraria o bloco cedo demais.
    bruto = bruto.replace("</", "<\\/")

    html = TEMPLATE.read_text(encoding="utf-8")
    if MARCADOR not in html:
        raise ValueError(f"marcador {MARCADOR!r} não encontrado no template")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html.replace(MARCADOR, bruto), encoding="utf-8")
    log.info("painel gerado: %s (%.1f KB)", destino, destino.stat().st_size / 1024)
    return destino


def tudo(base: Base) -> None:
    para_csv(base)
    para_xlsx(base)
    para_painel(base)
