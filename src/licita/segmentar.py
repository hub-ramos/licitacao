"""Classificação de itens e contratações em segmentos.

Ordem de precedência dos sinais, do mais confiável para o menos:

1. **Grupo CATMAT/CATSER** — código do catálogo federal preenchido pelo órgão.
   Quando existe, é inequívoco.
2. **Descrição do item** — casamento por palavra-chave.
3. **Objeto da contratação** — usado apenas quando o item não tem descrição útil,
   o que é comum em município pequeno que publica o edital com um item só.

Entre palavras-chave concorrentes vence a mais longa: "teste rapido de dengue"
deve ganhar de "teste rapido", e "camara de conservacao" de "camara".

O casamento é por **palavra inteira**, não por substring. A primeira versão usava
``palavra in texto`` e classificava "licenciamento de uso de software" como
material de construção, porque "cimento" está dentro de "licenCIMENTO" — três
contratações reais da Fase 0 caíram nisso. Como o segmento é o eixo do Índice de
Oportunidade, erro de segmento contamina toda a análise, em silêncio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .config import segmentos as cfg_segmentos
from .texto import normalizar

NAO_CLASSIFICADO = "nao_classificado"


@lru_cache(maxsize=4096)
def _padrao(palavra: str) -> re.Pattern[str]:
    """Compila uma palavra-chave em regex de palavra inteira, tolerando plural.

    ``normalizar`` já reduziu o texto a ``[0-9a-z ]``, então basta impedir que a
    vizinhança seja alfanumérica. O sufixo opcional aceita "cimentos" e "exames"
    sem aceitar "licenciamento".
    """
    return re.compile(
        r"(?<![0-9a-z])" + re.escape(palavra) + r"(?:e?s)?(?![0-9a-z])"
    )


def casa(palavra: str, texto_norm: str) -> bool:
    """Verdadeiro se ``palavra`` ocorre em ``texto_norm`` como palavra inteira."""
    return bool(palavra) and _padrao(palavra).search(texto_norm) is not None


@dataclass(frozen=True)
class Segmento:
    chave: str
    tipo: str            # produto | servico
    dominio: str
    aderencia: str       # alta | media | baixa | bloqueado
    nota: str
    bloqueio: str
    palavras: tuple[str, ...]
    excluir: tuple[str, ...]
    catmat: tuple[str, ...]
    catser: tuple[str, ...]

    @property
    def bloqueado(self) -> bool:
        return self.aderencia == "bloqueado"

    @property
    def de_saude(self) -> bool:
        return self.dominio == "saude"


@dataclass(frozen=True)
class Classificacao:
    segmento: str
    tipo: str
    dominio: str
    aderencia: str
    sinal: str           # catalogo | descricao | objeto | nenhum
    termo: str           # o que efetivamente casou, para auditoria

    @property
    def classificado(self) -> bool:
        return self.segmento != NAO_CLASSIFICADO


SEM_CLASSIFICACAO = Classificacao(
    segmento=NAO_CLASSIFICADO, tipo="indefinido", dominio="indefinido",
    aderencia="baixa", sinal="nenhum", termo="",
)


def _tupla(bruto: Any) -> tuple[str, ...]:
    if not bruto:
        return ()
    return tuple(str(v) for v in bruto)


def carregar() -> list[Segmento]:
    """Constrói os segmentos a partir do YAML, com palavras já normalizadas."""
    montados: list[Segmento] = []
    for chave, corpo in cfg_segmentos().items():
        if not isinstance(corpo, dict):
            continue
        montados.append(
            Segmento(
                chave=chave,
                tipo=corpo.get("tipo", "indefinido"),
                dominio=corpo.get("dominio", "indefinido"),
                aderencia=corpo.get("aderencia", "baixa"),
                nota=(corpo.get("nota") or "").strip(),
                bloqueio=(corpo.get("bloqueio") or "").strip(),
                palavras=tuple(normalizar(p) for p in _tupla(corpo.get("palavras"))),
                excluir=tuple(normalizar(p) for p in _tupla(corpo.get("excluir"))),
                catmat=_tupla(corpo.get("catmat")),
                catser=_tupla(corpo.get("catser")),
            )
        )
    return montados


class Classificador:
    """Reúne os segmentos e classifica textos. Instanciar uma vez e reutilizar."""

    def __init__(self, segmentos: list[Segmento] | None = None) -> None:
        self.segmentos = segmentos if segmentos is not None else carregar()
        self.por_chave = {s.chave: s for s in self.segmentos}

    # -------------------------------------------------------------- catálogo

    def _por_catalogo(self, catmat: str | None, catser: str | None) -> Segmento | None:
        """Casa pelo prefixo do grupo do catálogo federal. Prefixo mais longo vence."""
        melhor: tuple[int, Segmento] | None = None
        for codigo, campo in ((catmat, "catmat"), (catser, "catser")):
            digitos = "".join(ch for ch in str(codigo or "") if ch.isdigit())
            if not digitos:
                continue
            for seg in self.segmentos:
                for prefixo in getattr(seg, campo):
                    if digitos.startswith(prefixo) and (melhor is None or len(prefixo) > melhor[0]):
                        melhor = (len(prefixo), seg)
        return melhor[1] if melhor else None

    # ------------------------------------------------------------- palavras

    def _por_texto(self, texto_norm: str) -> tuple[Segmento, str] | None:
        if not texto_norm:
            return None
        melhor: tuple[int, Segmento, str] | None = None
        for seg in self.segmentos:
            if any(casa(veto, texto_norm) for veto in seg.excluir):
                continue
            for palavra in seg.palavras:
                if casa(palavra, texto_norm):
                    if melhor is None or len(palavra) > melhor[0]:
                        melhor = (len(palavra), seg, palavra)
        return (melhor[1], melhor[2]) if melhor else None

    # ------------------------------------------------------------ interface

    def classificar(
        self,
        descricao: str | None = None,
        objeto: str | None = None,
        catmat: str | None = None,
        catser: str | None = None,
    ) -> Classificacao:
        seg = self._por_catalogo(catmat, catser)
        if seg is not None:
            return self._montar(seg, "catalogo", str(catmat or catser or ""))

        achado = self._por_texto(normalizar(descricao))
        if achado is not None:
            return self._montar(achado[0], "descricao", achado[1])

        achado = self._por_texto(normalizar(objeto))
        if achado is not None:
            return self._montar(achado[0], "objeto", achado[1])

        return SEM_CLASSIFICACAO

    @staticmethod
    def _montar(seg: Segmento, sinal: str, termo: str) -> Classificacao:
        return Classificacao(
            segmento=seg.chave, tipo=seg.tipo, dominio=seg.dominio,
            aderencia=seg.aderencia, sinal=sinal, termo=termo,
        )


def orgao_de_saude(nome_orgao: str | None, nome_unidade: str | None = None) -> bool:
    """Detecta comprador da área de saúde.

    Importa porque compra de saúde costuma sair no CNPJ do Fundo Municipal de
    Saúde, que é distinto do CNPJ da prefeitura. Sem esta marcação, a análise de
    saúde perde justamente o órgão que mais compra saúde.
    """
    alvo = f"{normalizar(nome_orgao)} {normalizar(nome_unidade)}"
    marcadores = (
        "fundo municipal de saude",
        "secretaria municipal de saude",
        "secretaria de saude",
        "fundo de saude",
        "vigilancia sanitaria",
        "vigilancia epidemiologica",
        "hospital",
        "santa casa",
        "unidade basica de saude",
        "pronto socorro",
        "saude publica",
    )
    return any(m in alvo for m in marcadores)
