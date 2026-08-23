"""Normalização de texto, compartilhada entre resolução de municípios e segmentação."""

from __future__ import annotations

import re
import unicodedata

_ESPACOS = re.compile(r"\s+")
_NAO_ALFANUM = re.compile(r"[^0-9a-z ]+")


def normalizar(valor: object) -> str:
    """Minúsculas, sem acento, sem pontuação, espaços colapsados.

    É a forma canônica usada para comparar nomes de município e para casar
    palavras-chave de segmento contra descrições de item.
    """
    if valor is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = _NAO_ALFANUM.sub(" ", texto.lower())
    return _ESPACOS.sub(" ", texto).strip()


def apenas_digitos(valor: object) -> str:
    """Extrai dígitos — usado para normalizar CNPJ vindo com máscara."""
    return re.sub(r"\D", "", str(valor or ""))


def formatar_cnpj(cnpj: str) -> str:
    d = apenas_digitos(cnpj)
    if len(d) != 14:
        return cnpj
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
