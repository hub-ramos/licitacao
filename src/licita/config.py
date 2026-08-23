"""Carregamento dos arquivos de configuração YAML."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "config"
DADOS = RAIZ / "dados"
CACHE = RAIZ / ".cache"


def _ler(nome: str) -> dict[str, Any]:
    caminho = CONFIG / nome
    if not caminho.exists():
        raise FileNotFoundError(f"configuração ausente: {caminho}")
    with caminho.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@functools.cache
def fontes() -> dict[str, Any]:
    return _ler("fontes.yml")


@functools.cache
def municipios() -> dict[str, Any]:
    return _ler("municipios.yml")


@functools.cache
def segmentos() -> dict[str, Any]:
    return _ler("segmentos.yml")
