"""Cliente da API do Portal Nacional de Contratações Públicas.

Duas APIs distintas convivem aqui:

* **Consulta** (``/api/consulta``) — pública e documentada. Lista contratações,
  atas e contratos por período. É a fundação da base.
* **Detalhe** (``/api/pncp/v1``) — leitura pública, porém pior documentada.
  Entrega itens, resultados por item e arquivos de uma contratação específica.
  Os resultados por item são a única via estruturada para saber *quem ganhou e
  por quanto*, então valem o risco — mas o coletor degrada para o nível de
  contratação se estes caminhos não responderem como esperado.

Os endpoints de consulta foram exercitados contra a API real em 2026-08-24 e
respondem conforme o manual; os campos usados aqui foram conferidos no retorno.
O acesso a campo segue tolerante a ausência porque órgãos pequenos publicam com
preenchimento irregular, e um campo vazio não pode derrubar a varredura.

Duas restrições do manual que quebram a coleta em silêncio se ignoradas:

* ``tamanhoPagina`` tem **limite por endpoint** — 50 em ``/contratacoes/*``,
  500 em ``/atas`` e ``/contratos``, mínimo 10. Enviar 500 às contratações
  devolve HTTP 422 e a coleta volta vazia, sem parecer erro.
* ``codigoModalidadeContratacao`` é obrigatório em ``/contratacoes/publicacao``,
  por isso a coleta itera sobre modalidades em vez de pedir todas de uma vez.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterator

from .config import fontes
from .http import Cliente, Resposta
from .texto import apenas_digitos

log = logging.getLogger("licita.pncp")

# "01613202000171-1-000007/2026" -> cnpj, sequencial, ano
_CONTROLE = re.compile(r"^(\d{14})-(\d+)-(\d+)/(\d{4})$")


def partes_controle_pncp(numero: str | None) -> tuple[str, str, int] | None:
    """Decompõe ``numeroControlePNCP`` em (cnpj, sequencial, ano).

    É a ponte entre a API de consulta e a de detalhe: a consulta devolve o número
    de controle, e a de detalhe exige as três partes separadas na URL.
    """
    if not numero:
        return None
    m = _CONTROLE.match(str(numero).strip())
    if not m:
        return None
    cnpj, _tipo, sequencial, ano = m.groups()
    return cnpj, sequencial.lstrip("0") or "0", int(ano)


def link_pncp(numero: str | None) -> str | None:
    """URL canônica do PNCP para uma contratação, a partir de ``numeroControlePNCP``.

    Padrão confirmado em editais reais do portal:
    ``https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}``.
    Ao contrário de ``linkSistemaOrigem`` — publicado em só 8 das 102
    contratações do recorte de Santa Fé do Sul — esta URL existe para 100% das
    contratações, porque é montada a partir de um campo que a API sempre traz.
    """
    partes = partes_controle_pncp(numero)
    if not partes:
        return None
    cnpj, sequencial, ano = partes
    return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}"


def janelas(inicio: date, fim: date, dias: int) -> Iterator[tuple[date, date]]:
    """Fatia um intervalo em janelas fechadas de no máximo ``dias``."""
    if inicio > fim:
        return
    atual = inicio
    while atual <= fim:
        termino = min(atual + timedelta(days=dias - 1), fim)
        yield atual, termino
        atual = termino + timedelta(days=1)


def _aaaammdd(d: date) -> str:
    return d.strftime("%Y%m%d")


@dataclass
class Falha:
    """Registro de uma coleta parcial, para o relatório de cobertura."""

    contexto: str
    url: str
    status: int | None
    erro: str | None


class ClientePNCP:
    def __init__(self, cliente: Cliente | None = None) -> None:
        self.http = cliente or Cliente()
        cfg = fontes()["pncp"]
        self.consulta = cfg["consulta_base"]
        self.detalhe = cfg["detalhe_base"]
        self.rotas = cfg
        # Limite de paginação por endpoint. Ver comentário em config/fontes.yml:
        # aplicar 500 a /contratacoes/publicacao devolve 422 e a coleta volta vazia.
        self.tamanhos = cfg["tamanho_pagina"]
        self.janela_dias = cfg["janela_dias"]
        self.falhas: list[Falha] = []

    # ------------------------------------------------------------ utilitários

    def _registrar_falha(self, contexto: str, resp: Resposta) -> None:
        self.falhas.append(Falha(contexto, resp.url, resp.status, resp.erro))
        log.warning("falha em %s: %s %s", contexto, resp.status, resp.erro)

    def tamanho_pagina(self, endpoint: str) -> int:
        """Maior `tamanhoPagina` aceito pelo endpoint, conforme o manual do PNCP."""
        return self.tamanhos.get(endpoint, self.tamanhos.get("padrao", 50))

    def _coletar(self, url: str, params: dict, contexto: str) -> list[dict]:
        reunidos: list[dict] = []
        for registros, resp in self.http.paginar(url, params):
            if not resp.ok:
                self._registrar_falha(contexto, resp)
                break
            reunidos.extend(registros)
        return reunidos

    # ------------------------------------------------------- API de consulta

    def contratacoes_publicadas(
        self, codigo_ibge: str, modalidade: int, inicio: date, fim: date
    ) -> list[dict]:
        """Contratações publicadas no período, para um município e uma modalidade.

        ``codigoModalidadeContratacao`` é obrigatório na API — daí a coleta
        iterar sobre modalidades em vez de pedir todas de uma vez.
        """
        url = self.consulta + self.rotas["contratacoes_publicacao"]
        achados: list[dict] = []
        for jan_ini, jan_fim in janelas(inicio, fim, self.janela_dias):
            params = {
                "dataInicial": _aaaammdd(jan_ini),
                "dataFinal": _aaaammdd(jan_fim),
                "codigoModalidadeContratacao": modalidade,
                "codigoMunicipioIbge": codigo_ibge,
                "tamanhoPagina": self.tamanho_pagina("contratacoes_publicacao"),
            }
            ctx = f"contratacoes {codigo_ibge} mod={modalidade} {jan_ini}..{jan_fim}"
            achados.extend(self._coletar(url, params, ctx))
        return achados

    def contratacoes_com_proposta_aberta(
        self, codigo_ibge: str, modalidade: int, data_final: date
    ) -> list[dict]:
        """Contratações ainda recebendo proposta — a base do radar diário."""
        url = self.consulta + self.rotas["contratacoes_proposta"]
        params = {
            "dataFinal": _aaaammdd(data_final),
            "codigoModalidadeContratacao": modalidade,
            "codigoMunicipioIbge": codigo_ibge,
            "tamanhoPagina": self.tamanho_pagina("contratacoes_proposta"),
        }
        return self._coletar(url, params, f"proposta {codigo_ibge} mod={modalidade}")

    def atas(self, inicio: date, fim: date, cnpj: str | None = None) -> list[dict]:
        """Atas de registro de preço vigentes no período.

        O filtro é por vigência, não por município — por isso a seleção por
        município acontece depois, cruzando o CNPJ do órgão.
        """
        url = self.consulta + self.rotas["atas"]
        achados: list[dict] = []
        for jan_ini, jan_fim in janelas(inicio, fim, self.janela_dias):
            params = {
                "dataInicial": _aaaammdd(jan_ini),
                "dataFinal": _aaaammdd(jan_fim),
                "tamanhoPagina": self.tamanho_pagina("atas"),
            }
            if cnpj:
                params["cnpj"] = apenas_digitos(cnpj)
            achados.extend(self._coletar(url, params, f"atas {jan_ini}..{jan_fim}"))
        return achados

    def contratos(self, inicio: date, fim: date, cnpj_orgao: str | None = None) -> list[dict]:
        """Contratos publicados no período — traz fornecedor e valor global."""
        url = self.consulta + self.rotas["contratos"]
        achados: list[dict] = []
        for jan_ini, jan_fim in janelas(inicio, fim, self.janela_dias):
            params = {
                "dataInicial": _aaaammdd(jan_ini),
                "dataFinal": _aaaammdd(jan_fim),
                "tamanhoPagina": self.tamanho_pagina("contratos"),
            }
            if cnpj_orgao:
                params["cnpjOrgao"] = apenas_digitos(cnpj_orgao)
            achados.extend(self._coletar(url, params, f"contratos {jan_ini}..{jan_fim}"))
        return achados

    # -------------------------------------------------------- API de detalhe

    def itens(self, cnpj: str, ano: int, sequencial: str) -> list[dict]:
        """Itens de uma contratação, paginados.

        A distribuição de itens por contratação secava em 10 — 13 contratações
        do recorte de Santa Fé do Sul com exatamente 10 itens, nenhuma com
        mais — porque esta chamada fazia um GET simples sem ``pagina``, embora
        a rota aceite paginação (Manual de Integração do PNCP). ``/itens``
        devolve lista crua, não o envelope ``{data:[...]}`` das rotas de
        consulta; ``Cliente.paginar`` já trata os dois formatos.
        """
        url = self.detalhe + self.rotas["itens"].format(
            cnpj=apenas_digitos(cnpj), ano=ano, sequencial=sequencial
        )
        params = {"tamanhoPagina": self.tamanho_pagina("itens")}
        return self._coletar(url, params, f"itens {cnpj}/{ano}/{sequencial}")

    def resultados(self, cnpj: str, ano: int, sequencial: str, item: int) -> list[dict]:
        """Resultados (vencedores) de um item.

        Ausência de resultado é informação, não erro: item deserto ou fracassado
        legitimamente não tem vencedor. Por isso 404 e 204 devolvem lista vazia
        sem virar falha de coleta.
        """
        url = self.detalhe + self.rotas["resultados"].format(
            cnpj=apenas_digitos(cnpj), ano=ano, sequencial=sequencial, item=item
        )
        resp = self.http.obter(url)
        if resp.status == 404 or resp.vazio:
            return []
        if not resp.ok:
            self._registrar_falha(f"resultados {cnpj}/{ano}/{sequencial}/{item}", resp)
            return []
        return resp.dados if isinstance(resp.dados, list) else []

    def arquivos(self, cnpj: str, ano: int, sequencial: str) -> list[dict]:
        """Documentos publicados (edital, ata da sessão em PDF)."""
        url = self.detalhe + self.rotas["arquivos"].format(
            cnpj=apenas_digitos(cnpj), ano=ano, sequencial=sequencial
        )
        resp = self.http.obter(url)
        if resp.status == 404 or resp.vazio:
            return []
        if not resp.ok:
            self._registrar_falha(f"arquivos {cnpj}/{ano}/{sequencial}", resp)
            return []
        return resp.dados if isinstance(resp.dados, list) else []


def num(valor: Any) -> float | None:
    """Converte valor monetário/quantitativo do JSON para float, tolerando sujeira."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(" ", "")
    # "1.234,56" (pt-BR) -> "1234.56"; "1234.56" passa intacto
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None
