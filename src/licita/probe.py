"""Fase 0 — validação de endpoints e medição de cobertura.

Este módulo existe porque o código foi escrito sem acesso de rede às APIs
públicas brasileiras: o ambiente de desenvolvimento bloqueia todo host
``.gov.br``. Nada aqui pode ser tratado como confirmado até que este probe rode
num ambiente com acesso — o GitHub Actions.

O relatório responde quatro perguntas, em ordem de importância:

1. Os endpoints existem e devolvem o que a documentação promete?
2. O PNCP contém o pregão **presencial** de município pequeno? O caso-âncora
   (Nova Castilho, Pregão 007/2026, documentado de forma independente) é o teste.
   Se ele não aparecer, o cubo AUDESP do TCE-SP deixa de ser complemento e passa
   a ser obrigatório.
3. Qual a cobertura real por município, ano e modalidade?
4. Que tamanho tem o mercado de serviço técnico em saúde na região?
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .config import DADOS, fontes, municipios as cfg_municipios
from .http import Cliente
from .ibge import Municipio, resolver
from .pncp import ClientePNCP, _aaaammdd, partes_controle_pncp
from .segmentar import Classificador
from .texto import apenas_digitos, normalizar

log = logging.getLogger("licita.probe")

RELATORIO = DADOS / "relatorio_cobertura.md"
BRUTO = DADOS / "probe.json"


@dataclass
class Sonda:
    nome: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    status: int | None = None
    ok: bool = False
    registros: int | None = None
    campos: list[str] = field(default_factory=list)
    erro: str | None = None
    observacao: str = ""

    @property
    def veredito(self) -> str:
        if self.ok and self.registros:
            return "OK"
        if self.ok:
            return "VAZIO"
        return "FALHA"


def _campos_do_primeiro(dados: Any) -> tuple[int | None, list[str]]:
    """Extrai contagem e nomes de campo do primeiro registro, seja lista ou envelope."""
    if isinstance(dados, dict) and isinstance(dados.get("data"), list):
        registros = dados["data"]
    elif isinstance(dados, list):
        registros = dados
    else:
        return (None, sorted(dados)[:40] if isinstance(dados, dict) else [])
    if not registros:
        return (0, [])
    primeiro = registros[0]
    return (len(registros), sorted(primeiro)[:40] if isinstance(primeiro, dict) else [])


class Probe:
    def __init__(self) -> None:
        self.http = Cliente(usar_cache=False)   # probe sempre bate na origem
        self.pncp = ClientePNCP(self.http)
        self.sondas: list[Sonda] = []
        self.municipios: list[Municipio] = []
        self.ancora: dict[str, Any] = {}
        self.cobertura: list[dict] = []
        self.mercado_servico: list[dict] = []

    # ------------------------------------------------------------- endpoints

    def _sondar(self, nome: str, url: str, params: dict | None = None, obs: str = "") -> Sonda:
        resp = self.http.obter(url, params)
        registros, campos = _campos_do_primeiro(resp.dados)
        sonda = Sonda(
            nome=nome, url=url, params=params or {}, status=resp.status,
            ok=resp.ok, registros=registros, campos=campos,
            erro=resp.erro, observacao=obs,
        )
        self.sondas.append(sonda)
        log.info("[%s] %s -> %s", sonda.veredito, nome, resp.status)
        return sonda

    def sondar_endpoints(self) -> None:
        cfg = fontes()
        f_ibge, f_pncp = cfg["ibge"], cfg["pncp"]
        uf = cfg_municipios()["codigo_uf_ibge"]

        self._sondar(
            "IBGE · municípios da UF",
            f_ibge["base"] + f_ibge["municipios_por_uf"].format(uf=uf),
            obs="Resolve os códigos IBGE dos municípios-alvo.",
        )

        fim = date.today()
        inicio = fim - timedelta(days=cfg["pncp"]["janela_dias"])
        ancora = cfg_municipios()["caso_ancora"]

        self._sondar(
            "PNCP · contratações por publicação",
            f_pncp["consulta_base"] + f_pncp["contratacoes_publicacao"],
            {
                "dataInicial": _aaaammdd(inicio), "dataFinal": _aaaammdd(fim),
                "codigoModalidadeContratacao": 7, "uf": "SP",
                "pagina": 1, "tamanhoPagina": 10,
            },
            obs="Fundação do histórico. Modalidade 7 = pregão presencial.",
        )
        self._sondar(
            "PNCP · contratações com proposta aberta",
            f_pncp["consulta_base"] + f_pncp["contratacoes_proposta"],
            {
                "dataFinal": _aaaammdd(fim + timedelta(days=60)),
                "codigoModalidadeContratacao": 6, "uf": "SP",
                "pagina": 1, "tamanhoPagina": 10,
            },
            obs="Base do radar diário de oportunidades.",
        )
        self._sondar(
            "PNCP · atas de registro de preço",
            f_pncp["consulta_base"] + f_pncp["atas"],
            {
                "dataInicial": _aaaammdd(inicio), "dataFinal": _aaaammdd(fim),
                "pagina": 1, "tamanhoPagina": 10,
            },
        )
        self._sondar(
            "PNCP · contratos",
            f_pncp["consulta_base"] + f_pncp["contratos"],
            {
                "dataInicial": _aaaammdd(inicio), "dataFinal": _aaaammdd(fim),
                "pagina": 1, "tamanhoPagina": 10,
            },
            obs="Traz niFornecedor e valorGlobal: é a fonte de quem ganha o quê.",
        )

        # Rotas de detalhe: as menos confirmadas. Testadas contra o caso-âncora.
        cnpj = apenas_digitos(ancora["cnpj_orgao"])
        ano = ancora["ano"]
        seq = self.ancora.get("sequencial")
        if seq:
            self._sondar(
                "PNCP · itens da contratação",
                f_pncp["detalhe_base"] + f_pncp["itens"].format(cnpj=cnpj, ano=ano, sequencial=seq),
                obs="Caminho não confirmado em documentação oficial estável.",
            )
            self._sondar(
                "PNCP · resultados do item 1",
                f_pncp["detalhe_base"] + f_pncp["resultados"].format(
                    cnpj=cnpj, ano=ano, sequencial=seq, item=1),
                obs="Única via estruturada para vencedor e valor homologado por item.",
            )
            self._sondar(
                "PNCP · arquivos da contratação",
                f_pncp["detalhe_base"] + f_pncp["arquivos"].format(cnpj=cnpj, ano=ano, sequencial=seq),
                obs="Edital e ata em PDF; insumo do parser de contagem de licitantes.",
            )
        else:
            self.sondas.append(Sonda(
                nome="PNCP · rotas de detalhe (itens/resultados/arquivos)",
                url=f_pncp["detalhe_base"] + f_pncp["itens"],
                erro="não testadas: o caso-âncora não foi localizado na API de consulta",
                observacao="Sem o sequencial da contratação não há como montar a URL.",
            ))

    # ----------------------------------------------------------- caso-âncora

    def testar_caso_ancora(self) -> dict[str, Any]:
        """Procura no PNCP o Pregão Presencial 007/2026 de Nova Castilho.

        É o único ponto do projeto com verdade conhecida de forma independente
        (documentada no handoff a partir dos PDFs oficiais). Se o PNCP não o
        contiver, a base não serve para pregão presencial de município pequeno —
        que é justamente o padrão da região.
        """
        cfg = cfg_municipios()["caso_ancora"]
        cnpj = apenas_digitos(cfg["cnpj_orgao"])
        ano = cfg["ano"]
        alvo_numero = normalizar(cfg["numero_compra"])

        resultado: dict[str, Any] = {
            "procurado": {
                "municipio": cfg["municipio"], "cnpj_orgao": cnpj,
                "numero_compra": cfg["numero_compra"], "modalidade": cfg["modalidade"],
            },
            "encontrado": False,
            "verdade_conhecida": {
                "valor_unitario_estimado": cfg["valor_unitario_estimado"],
                "valor_unitario_homologado": cfg["valor_unitario_homologado"],
                "quantidade_total": cfg["quantidade_total"],
                "valor_total_ata": cfg["valor_total_ata"],
                "licitantes_presentes": cfg["licitantes_presentes"],
            },
        }

        # Varre o ano inteiro do caso, em todas as modalidades configuradas: o
        # município pode ter publicado sob modalidade diferente da esperada.
        for modalidade in fontes()["pncp"]["modalidades"]:
            achados = self.pncp.contratacoes_publicadas(
                self._ibge_ancora(), modalidade, date(ano, 1, 1), date(ano, 12, 31)
            )
            for bruto in achados:
                numero = normalizar(bruto.get("numeroCompra"))
                objeto = normalizar(bruto.get("objetoCompra"))
                casa_numero = alvo_numero and alvo_numero in numero
                casa_objeto = cfg["objeto_contem"] in objeto
                if not (casa_numero or casa_objeto):
                    continue
                controle = bruto.get("numeroControlePNCP")
                partes = partes_controle_pncp(controle)
                resultado.update({
                    "encontrado": True,
                    "numero_controle_pncp": controle,
                    "modalidade_publicada": bruto.get("modalidadeId"),
                    "modalidade_nome": bruto.get("modalidadeNome"),
                    "numero_compra": bruto.get("numeroCompra"),
                    "objeto": bruto.get("objetoCompra"),
                    "valor_total_estimado": bruto.get("valorTotalEstimado"),
                    "valor_total_homologado": bruto.get("valorTotalHomologado"),
                    "casou_por": "numero" if casa_numero else "objeto",
                })
                if partes:
                    self.ancora["sequencial"] = partes[1]
                    resultado["sequencial"] = partes[1]
                self.ancora.update(resultado)
                return resultado

        self.ancora.update(resultado)
        return resultado

    def _ibge_ancora(self) -> str:
        alvo = normalizar(cfg_municipios()["caso_ancora"]["municipio"])
        for m in self.municipios:
            if normalizar(m.nome) == alvo:
                return m.codigo_ibge
        return ""

    # ------------------------------------------------------------- cobertura

    def medir_cobertura(self, anos: int = 3) -> None:
        """Conta contratações por município × ano × modalidade, sem gravar detalhe."""
        hoje = date.today()
        for mun in self.municipios:
            for ano in range(hoje.year - anos + 1, hoje.year + 1):
                fim = min(date(ano, 12, 31), hoje)
                for modalidade in fontes()["pncp"]["modalidades"]:
                    achados = self.pncp.contratacoes_publicadas(
                        mun.codigo_ibge, modalidade, date(ano, 1, 1), fim
                    )
                    if not achados:
                        continue
                    self.cobertura.append({
                        "municipio": mun.nome,
                        "codigo_ibge": mun.codigo_ibge,
                        "ano": ano,
                        "modalidade": modalidade,
                        "contratacoes": len(achados),
                        "valor_estimado": sum(
                            float(a.get("valorTotalEstimado") or 0) for a in achados
                        ),
                    })

    def sondar_mercado_servico(self, anos: int = 2) -> None:
        """Dimensiona o mercado de serviço técnico em saúde da região.

        Conta contratações em dispensa, inexigibilidade e credenciamento cujo
        objeto classifica como serviço do domínio saúde. É o que diz se a segunda
        linha de negócio tem tamanho, antes de qualquer investimento nela.
        """
        classificador = Classificador()
        modalidades = fontes().get("modalidades_servico_tecnico", [8, 9, 12])
        hoje = date.today()
        inicio = date(hoje.year - anos, hoje.month, 1)

        for mun in self.municipios:
            for modalidade in modalidades:
                for bruto in self.pncp.contratacoes_publicadas(
                    mun.codigo_ibge, modalidade, inicio, hoje
                ):
                    objeto = bruto.get("objetoCompra") or ""
                    cls = classificador.classificar(objeto=objeto)
                    if cls.tipo != "servico" or cls.dominio != "saude":
                        continue
                    self.mercado_servico.append({
                        "municipio": mun.nome,
                        "modalidade": modalidade,
                        "segmento": cls.segmento,
                        "objeto": objeto[:200],
                        "valor_estimado": bruto.get("valorTotalEstimado"),
                        "data": bruto.get("dataPublicacaoPncp"),
                    })

    # ------------------------------------------------------------- execução

    def executar(self, anos: int = 3, completo: bool = True) -> None:
        self.municipios = resolver(self.http, forcar=True)
        log.info("municípios-alvo resolvidos: %d", len(self.municipios))
        self.testar_caso_ancora()
        self.sondar_endpoints()
        if completo:
            self.medir_cobertura(anos=anos)
            self.sondar_mercado_servico()

    # ------------------------------------------------------------ relatório

    def escrever(self) -> None:
        DADOS.mkdir(parents=True, exist_ok=True)
        BRUTO.write_text(
            json.dumps(
                {
                    "sondas": [vars(s) for s in self.sondas],
                    "caso_ancora": self.ancora,
                    "cobertura": self.cobertura,
                    "mercado_servico": self.mercado_servico,
                    "municipios": [vars(m) for m in self.municipios],
                },
                ensure_ascii=False, indent=2, default=str,
            ) + "\n",
            encoding="utf-8",
        )
        RELATORIO.write_text(self._markdown(), encoding="utf-8")
        log.info("relatório escrito em %s", RELATORIO)

    def _markdown(self) -> str:
        from .relatorio import montar
        return montar(self)
