"""Persistência em SQLite.

Toda escrita é idempotente: reexecutar a coleta sobre o mesmo período atualiza
as linhas existentes em vez de duplicá-las. Isso é requisito, não conveniência —
a coleta é incremental e roda em cima de si mesma todo dia.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import DADOS, RAIZ

ARQUIVO_PADRAO = DADOS / "licitacoes.db"
ESQUEMA = RAIZ / "sql" / "schema.sql"

# Colunas que compõem a chave primária de cada tabela, para o upsert.
CHAVES: dict[str, tuple[str, ...]] = {
    "municipio": ("codigo_ibge",),
    "orgao": ("cnpj",),
    "fornecedor": ("ni",),
    "contratacao": ("numero_controle_pncp",),
    "item": ("numero_controle_pncp", "numero_item"),
    "resultado": ("numero_controle_pncp", "numero_item", "sequencial_resultado"),
    "ata": ("numero_controle_pncp_ata",),
    "contrato": ("numero_controle_pncp",),
    "arquivo": ("numero_controle_pncp", "sequencial"),
    "metrica_mun_seg_ano": ("codigo_ibge", "segmento", "ano"),
    "cobertura": ("codigo_ibge", "ano", "modalidade_id"),
}

# Colunas aditivas introduzidas depois que `dados/licitacoes.db` já estava
# commitado. `CREATE TABLE IF NOT EXISTS` não adiciona coluna a uma tabela
# existente — sem isto, uma base antiga reaberta ficaria sem a coluna e o
# upsert falharia com "no such column". A regra do projeto é que coluna nova
# é sempre aditiva e nunca remove ou renomeia uma existente; isto é a
# contrapartida em runtime dessa regra.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("contratacao", "link_pncp", "TEXT"),
)


def agora() -> str:
    """Carimbo UTC em ISO-8601, usado em todas as colunas ``*_em``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Base:
    def __init__(self, caminho: Path | str = ARQUIVO_PADRAO) -> None:
        self.caminho = Path(caminho)
        if self.caminho != Path(":memory:"):
            self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.caminho))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self._criar_esquema()

    def _criar_esquema(self) -> None:
        self.con.executescript(ESQUEMA.read_text(encoding="utf-8"))
        self._migrar()
        self.con.commit()

    def _migrar(self) -> None:
        """Aplica colunas aditivas que a base já existente ainda não tem."""
        for tabela, coluna, tipo in MIGRACOES:
            existentes = {r[1] for r in self.con.execute(f"PRAGMA table_info({tabela})")}
            if coluna not in existentes:
                self.con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")

    # ------------------------------------------------------------- escrita

    def upsert(self, tabela: str, registro: dict[str, Any]) -> None:
        self.upsert_muitos(tabela, [registro])

    def upsert_muitos(self, tabela: str, registros: Sequence[dict[str, Any]]) -> int:
        """Insere ou atualiza em lote. Devolve quantas linhas foram processadas.

        Todos os registros do lote precisam ter o mesmo conjunto de colunas; a
        função agrupa por assinatura de colunas para tolerar variação entre eles.
        """
        if not registros:
            return 0
        chaves = CHAVES.get(tabela)
        if not chaves:
            raise KeyError(f"tabela sem chave primária declarada em CHAVES: {tabela}")

        por_assinatura: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for reg in registros:
            por_assinatura.setdefault(tuple(sorted(reg)), []).append(reg)

        total = 0
        for colunas_ord, lote in por_assinatura.items():
            colunas = list(colunas_ord)
            faltando = [c for c in chaves if c not in colunas]
            if faltando:
                raise ValueError(f"{tabela}: registro sem as chaves {faltando}")

            atualizaveis = [c for c in colunas if c not in chaves]
            sql = (
                f"INSERT INTO {tabela} ({', '.join(colunas)}) "
                f"VALUES ({', '.join('?' * len(colunas))}) "
                f"ON CONFLICT ({', '.join(chaves)}) DO "
            )
            if atualizaveis:
                sql += "UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in atualizaveis)
            else:
                sql += "NOTHING"

            self.con.executemany(sql, [[reg[c] for c in colunas] for reg in lote])
            total += len(lote)

        self.con.commit()
        return total

    def registrar_falhas(self, execucao: str, falhas: Iterable[Any]) -> int:
        """Grava falhas de coleta para o relatório de cobertura."""
        linhas = [
            (execucao, f.contexto, f.url, f.status, f.erro, agora())
            for f in falhas
        ]
        if not linhas:
            return 0
        self.con.executemany(
            "INSERT INTO coleta_log (execucao, contexto, url, status, erro, criado_em)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            linhas,
        )
        self.con.commit()
        return len(linhas)

    # ------------------------------------------------------------- leitura

    def consultar(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.con.execute(sql, params))

    def valor(self, sql: str, params: Sequence[Any] = ()) -> Any:
        linha = self.con.execute(sql, params).fetchone()
        return linha[0] if linha else None

    def contar(self, tabela: str) -> int:
        return int(self.valor(f"SELECT COUNT(*) FROM {tabela}") or 0)

    # ------------------------------------------------------------ ciclo de vida

    def fechar(self) -> None:
        self.con.close()

    def __enter__(self) -> "Base":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.fechar()
