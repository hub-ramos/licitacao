"""Orquestra a coleta: PNCP -> classificação -> SQLite.

Os nomes de campo do JSON do PNCP não puderam ser verificados ao vivo durante a
escrita. Por isso todo acesso passa por :func:`pega`, que aceita uma lista de
nomes alternativos e devolve o primeiro que existir. Um campo ausente vira
``None`` na base — nunca uma exceção que derruba a varredura inteira.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

from .config import fontes, municipios as cfg_municipios
from .db import Base, agora
from .ibge import Municipio
from .pncp import ClientePNCP, num, partes_controle_pncp
from .segmentar import Classificador, orgao_de_saude
from .texto import apenas_digitos

log = logging.getLogger("licita.coleta")


def pega(dic: Any, *nomes: str, padrao: Any = None) -> Any:
    """Primeiro campo presente entre ``nomes``, aceitando caminho com ponto."""
    if not isinstance(dic, dict):
        return padrao
    for nome in nomes:
        no: Any = dic
        for parte in nome.split("."):
            no = no.get(parte) if isinstance(no, dict) else None
            if no is None:
                break
        if no not in (None, ""):
            return no
    return padrao


def _bool(valor: Any) -> int:
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, (int, float)):
        return int(bool(valor))
    return int(str(valor).strip().lower() in {"true", "sim", "s", "1"})


def _data(valor: Any) -> str | None:
    """Mantém a data como texto ISO. Corta o fuso, que não interessa à análise."""
    if not valor:
        return None
    texto = str(valor).strip()
    return texto[:19] if len(texto) > 19 else texto


@dataclass
class Resumo:
    """Contagens de uma execução, para log e para o relatório."""

    contratacoes: int = 0
    itens: int = 0
    resultados: int = 0
    atas: int = 0
    contratos: int = 0
    municipios: int = 0
    falhas: int = 0
    sem_detalhe: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"{self.municipios} municípios · {self.contratacoes} contratações · "
            f"{self.itens} itens · {self.resultados} resultados · "
            f"{self.atas} atas · {self.contratos} contratos · {self.falhas} falhas"
        )


class Coletor:
    def __init__(self, base: Base, pncp: ClientePNCP | None = None) -> None:
        self.base = base
        self.pncp = pncp or ClientePNCP()
        self.classificador = Classificador()
        cfg = fontes()
        self.modalidades = cfg["pncp"]["modalidades"]
        self.presenciais = set(cfg.get("modalidades_presenciais", []))
        self.resumo = Resumo()

    # ------------------------------------------------------------ dimensões

    def gravar_municipios(self, lista: Iterable[Municipio]) -> int:
        linhas = [
            {
                "codigo_ibge": m.codigo_ibge,
                "nome": m.nome,
                "uf": m.uf,
                "regiao_imediata": m.regiao_imediata,
                "regiao_intermediaria": m.regiao_intermediaria,
                "motivo_inclusao": m.motivo_inclusao,
                "prioritario": int(m.prioritario),
            }
            for m in lista
        ]
        self.resumo.municipios = len(linhas)
        return self.base.upsert_muitos("municipio", linhas)

    def _gravar_orgao(self, bruto: dict, codigo_ibge: str, de_saude: bool) -> str | None:
        cnpj = apenas_digitos(pega(bruto, "orgaoEntidade.cnpj", "cnpjOrgao", "cnpj"))
        if not cnpj:
            return None
        self.base.upsert(
            "orgao",
            {
                "cnpj": cnpj,
                "razao_social": pega(bruto, "orgaoEntidade.razaoSocial", "nomeOrgao", "razaoSocial"),
                "codigo_ibge": codigo_ibge or None,
                "esfera": pega(bruto, "orgaoEntidade.esferaId", "esferaId"),
                "poder": pega(bruto, "orgaoEntidade.poderId", "poderId"),
                "de_saude": int(de_saude),
            },
        )
        return cnpj

    # -------------------------------------------------------- contratações

    def _linha_contratacao(self, bruto: dict, codigo_ibge: str) -> dict | None:
        controle = pega(bruto, "numeroControlePNCP", "numeroControlePncp")
        if not controle:
            return None

        partes = partes_controle_pncp(controle)
        cnpj_fallback, sequencial, ano_controle = partes or ("", "", None)

        nome_orgao = pega(bruto, "orgaoEntidade.razaoSocial", "nomeOrgao")
        nome_unidade = pega(bruto, "unidadeOrgao.nomeUnidade", "nomeUnidade")
        de_saude = orgao_de_saude(nome_orgao, nome_unidade)

        # O código IBGE do payload manda sobre o do laço: o filtro da API é pela
        # unidade do órgão, e confirmá-lo evita gravar município errado.
        ibge_payload = str(pega(bruto, "unidadeOrgao.codigoIbge", "codigoIbge", padrao="") or "")
        ibge = ibge_payload or codigo_ibge

        cnpj = self._gravar_orgao(bruto, ibge, de_saude) or cnpj_fallback
        modalidade = pega(bruto, "modalidadeId", "codigoModalidadeContratacao")

        return {
            "numero_controle_pncp": controle,
            "cnpj_orgao": cnpj or None,
            "codigo_ibge": ibge or None,
            "ano": pega(bruto, "anoCompra", padrao=ano_controle),
            "sequencial": str(pega(bruto, "sequencialCompra", padrao=sequencial) or ""),
            "numero_compra": pega(bruto, "numeroCompra"),
            "processo": pega(bruto, "processo"),
            "modalidade_id": modalidade,
            "modalidade_nome": pega(bruto, "modalidadeNome"),
            "presencial": int(modalidade in self.presenciais),
            "modo_disputa_id": pega(bruto, "modoDisputaId"),
            "modo_disputa_nome": pega(bruto, "modoDisputaNome"),
            "situacao_id": pega(bruto, "situacaoCompraId"),
            "situacao_nome": pega(bruto, "situacaoCompraNome"),
            "srp": _bool(pega(bruto, "srp", padrao=False)),
            "objeto": pega(bruto, "objetoCompra", "objeto"),
            "valor_total_estimado": num(pega(bruto, "valorTotalEstimado")),
            "valor_total_homologado": num(pega(bruto, "valorTotalHomologado")),
            "data_publicacao": _data(pega(bruto, "dataPublicacaoPncp", "dataInclusao")),
            "data_abertura_proposta": _data(pega(bruto, "dataAberturaProposta")),
            "data_encerramento_proposta": _data(pega(bruto, "dataEncerramentoProposta")),
            "unidade_nome": nome_unidade,
            "unidade_codigo": pega(bruto, "unidadeOrgao.codigoUnidade", "codigoUnidade"),
            "orgao_de_saude": int(de_saude),
            "amparo_legal": pega(bruto, "amparoLegal.descricao", "amparoLegal.nome"),
            "link_sistema_origem": pega(bruto, "linkSistemaOrigem"),
            "coletado_em": agora(),
        }

    # ---------------------------------------------------------------- itens

    def _linha_item(self, bruto: dict, controle: str, objeto: str | None) -> dict | None:
        numero = pega(bruto, "numeroItem", "numero")
        if numero is None:
            return None

        descricao = pega(bruto, "descricao", "descricaoItem", "materialOuServicoNome")
        catmat = pega(bruto, "catalogoCodigoItem", "codigoItemCatalogo", "catmat")
        catser = pega(bruto, "codigoServico", "catser")

        cls = self.classificador.classificar(
            descricao=descricao, objeto=objeto, catmat=catmat, catser=catser
        )

        return {
            "numero_controle_pncp": controle,
            "numero_item": int(numero),
            "descricao": descricao,
            "unidade_medida": pega(bruto, "unidadeMedida"),
            "quantidade": num(pega(bruto, "quantidade")),
            "valor_unitario_estimado": num(pega(bruto, "valorUnitarioEstimado")),
            "valor_total_estimado": num(pega(bruto, "valorTotal", "valorTotalEstimado")),
            "situacao_item_id": pega(bruto, "situacaoCompraItemId", "situacaoCompraItem"),
            "situacao_item_nome": pega(bruto, "situacaoCompraItemNome"),
            "tipo_beneficio_id": pega(bruto, "tipoBeneficioId"),
            "tipo_beneficio_nome": pega(bruto, "tipoBeneficioNome"),
            "criterio_julgamento": pega(bruto, "criterioJulgamentoNome"),
            "catmat": str(catmat) if catmat else None,
            "catser": str(catser) if catser else None,
            "segmento": cls.segmento,
            "tipo_segmento": cls.tipo,
            "dominio": cls.dominio,
            "aderencia": cls.aderencia,
            "sinal_classificacao": cls.sinal,
            "termo_classificacao": cls.termo,
            "coletado_em": agora(),
        }

    def _linha_resultado(self, bruto: dict, controle: str, item: int, ordem: int) -> dict:
        ni = apenas_digitos(pega(bruto, "niFornecedor", "nifornecedor", "cnpjCpfFornecedor"))
        nome = pega(bruto, "nomeRazaoSocialFornecedor", "nomeFornecedor")
        porte = pega(bruto, "porteFornecedorNome", "porteFornecedor")

        if ni:
            self.base.upsert("fornecedor", {"ni": ni, "nome": nome, "porte": porte})

        return {
            "numero_controle_pncp": controle,
            "numero_item": item,
            "sequencial_resultado": int(pega(bruto, "sequencialResultado", padrao=ordem)),
            "ni_fornecedor": ni or None,
            "nome_fornecedor": nome,
            "porte_fornecedor": porte,
            "quantidade_homologada": num(pega(bruto, "quantidadeHomologada")),
            "valor_unitario_homologado": num(pega(bruto, "valorUnitarioHomologado")),
            "valor_total_homologado": num(pega(bruto, "valorTotalHomologado")),
            "data_resultado": _data(pega(bruto, "dataResultado")),
            "coletado_em": agora(),
        }

    def coletar_detalhe(self, contratacao: dict) -> None:
        """Busca itens, resultados e arquivos de uma contratação já gravada."""
        controle = contratacao["numero_controle_pncp"]
        partes = partes_controle_pncp(controle)
        if not partes:
            self.resumo.sem_detalhe.append(controle)
            return
        cnpj, sequencial, ano = partes
        objeto = contratacao.get("objeto")

        itens = self.pncp.itens(cnpj, ano, sequencial)
        if not itens:
            self.resumo.sem_detalhe.append(controle)
            return

        linhas_item = [
            linha for bruto in itens
            if (linha := self._linha_item(bruto, controle, objeto)) is not None
        ]
        self.resumo.itens += self.base.upsert_muitos("item", linhas_item)

        linhas_resultado: list[dict] = []
        for linha in linhas_item:
            numero = linha["numero_item"]
            # Item deserto ou fracassado não tem vencedor; poupa uma chamada.
            if linha["situacao_item_id"] in (4, 5):
                continue
            for ordem, bruto in enumerate(
                self.pncp.resultados(cnpj, ano, sequencial, numero), start=1
            ):
                linhas_resultado.append(self._linha_resultado(bruto, controle, numero, ordem))
        self.resumo.resultados += self.base.upsert_muitos("resultado", linhas_resultado)

        arquivos = [
            {
                "numero_controle_pncp": controle,
                "sequencial": int(pega(bruto, "sequencialDocumento", padrao=ordem)),
                "titulo": pega(bruto, "titulo", "nomeArquivo"),
                "tipo_documento": pega(bruto, "tipoDocumentoNome", "tipoDocumentoDescricao"),
                "url": pega(bruto, "url", "uri", "link"),
                "data_publicacao": _data(pega(bruto, "dataPublicacaoPncp")),
                "coletado_em": agora(),
            }
            for ordem, bruto in enumerate(self.pncp.arquivos(cnpj, ano, sequencial), start=1)
        ]
        self.base.upsert_muitos("arquivo", arquivos)

    # ------------------------------------------------------------ varreduras

    def coletar_historico(
        self, alvos: list[Municipio], inicio: date, fim: date, com_detalhe: bool = True
    ) -> Resumo:
        """Backfill de contratações publicadas, por município e modalidade."""
        for mun in alvos:
            for modalidade in self.modalidades:
                brutos = self.pncp.contratacoes_publicadas(
                    mun.codigo_ibge, modalidade, inicio, fim
                )
                linhas = [
                    linha for b in brutos
                    if (linha := self._linha_contratacao(b, mun.codigo_ibge)) is not None
                ]
                if not linhas:
                    continue
                self.resumo.contratacoes += self.base.upsert_muitos("contratacao", linhas)
                log.info("%s mod=%s: %d contratações", mun.rotulo, modalidade, len(linhas))

                if com_detalhe:
                    for linha in linhas:
                        self.coletar_detalhe(linha)

        self._encerrar()
        return self.resumo

    def coletar_radar(self, alvos: list[Municipio], horizonte_dias: int | None = None) -> Resumo:
        """Contratações com proposta ainda em aberto — varredura diária, rápida."""
        dias = horizonte_dias or fontes()["coleta"]["radar_horizonte_dias"]
        limite = date.today() + timedelta(days=dias)

        for mun in alvos:
            for modalidade in self.modalidades:
                brutos = self.pncp.contratacoes_com_proposta_aberta(
                    mun.codigo_ibge, modalidade, limite
                )
                linhas = [
                    linha for b in brutos
                    if (linha := self._linha_contratacao(b, mun.codigo_ibge)) is not None
                ]
                if linhas:
                    self.resumo.contratacoes += self.base.upsert_muitos("contratacao", linhas)
                    for linha in linhas:
                        self.coletar_detalhe(linha)

        self._encerrar()
        return self.resumo

    def coletar_atas_e_contratos(self, alvos: list[Municipio], inicio: date, fim: date) -> Resumo:
        """Atas e contratos do período, filtrados aos órgãos dos municípios-alvo.

        A API não filtra atas por município, então a seleção é feita depois, pelo
        CNPJ do órgão já conhecido — o que exige ter coletado contratações antes.
        """
        cnpjs = {
            linha["cnpj"]
            for linha in self.base.consultar(
                "SELECT cnpj FROM orgao WHERE codigo_ibge IN "
                f"({','.join('?' * len(alvos))})",
                [m.codigo_ibge for m in alvos],
            )
        }
        if not cnpjs:
            log.warning("nenhum órgão conhecido; colete contratações antes de atas/contratos")
            return self.resumo

        por_cnpj = {
            linha["cnpj"]: linha["codigo_ibge"]
            for linha in self.base.consultar("SELECT cnpj, codigo_ibge FROM orgao")
        }

        for cnpj in sorted(cnpjs):
            atas = [
                {
                    "numero_controle_pncp_ata": pega(b, "numeroControlePNCPAta", "numeroControlePncpAta"),
                    "numero_controle_pncp_compra": pega(b, "numeroControlePNCPCompra"),
                    "numero_ata": pega(b, "numeroAtaRegistroPreco"),
                    "ano_ata": pega(b, "anoAta"),
                    "cnpj_orgao": apenas_digitos(pega(b, "cnpjOrgao", padrao=cnpj)),
                    "nome_orgao": pega(b, "nomeOrgao"),
                    "codigo_ibge": por_cnpj.get(cnpj),
                    "objeto": pega(b, "objetoContratacao", "objeto"),
                    "data_assinatura": _data(pega(b, "dataAssinatura")),
                    "vigencia_inicio": _data(pega(b, "vigenciaInicio")),
                    "vigencia_fim": _data(pega(b, "vigenciaFim")),
                    "cancelado": _bool(pega(b, "cancelado", padrao=False)),
                    "data_cancelamento": _data(pega(b, "dataCancelamento")),
                    "coletado_em": agora(),
                }
                for b in self.pncp.atas(inicio, fim, cnpj)
            ]
            atas = [a for a in atas if a["numero_controle_pncp_ata"]]
            self.resumo.atas += self.base.upsert_muitos("ata", atas)

            contratos: list[dict] = []
            for b in self.pncp.contratos(inicio, fim, cnpj):
                controle = pega(b, "numeroControlePNCP", "numeroControlePncp")
                if not controle:
                    continue
                ni = apenas_digitos(pega(b, "niFornecedor"))
                nome_forn = pega(b, "nomeRazaoSocialFornecedor")
                if ni:
                    self.base.upsert("fornecedor", {"ni": ni, "nome": nome_forn, "porte": None})
                objeto = pega(b, "objetoContrato", "objeto")
                cls = self.classificador.classificar(objeto=objeto)
                contratos.append({
                    "numero_controle_pncp": controle,
                    "numero_contrato": pega(b, "numeroContratoEmpenho"),
                    "ano_contrato": pega(b, "anoContrato"),
                    "cnpj_orgao": apenas_digitos(pega(b, "orgaoEntidade.cnpj", "cnpjOrgao", padrao=cnpj)),
                    "nome_orgao": pega(b, "orgaoEntidade.razaoSocial", "nomeOrgao"),
                    "codigo_ibge": por_cnpj.get(cnpj),
                    "ni_fornecedor": ni or None,
                    "nome_fornecedor": nome_forn,
                    "objeto": objeto,
                    "valor_global": num(pega(b, "valorGlobal", "valorInicial")),
                    "data_assinatura": _data(pega(b, "dataAssinatura")),
                    "vigencia_inicio": _data(pega(b, "dataVigenciaInicio")),
                    "vigencia_fim": _data(pega(b, "dataVigenciaFim")),
                    "data_publicacao": _data(pega(b, "dataPublicacaoPncp")),
                    "segmento": cls.segmento,
                    "tipo_segmento": cls.tipo,
                    "coletado_em": agora(),
                })
            self.resumo.contratos += self.base.upsert_muitos("contrato", contratos)

        self._encerrar()
        return self.resumo

    # --------------------------------------------------------------- apoio

    def _encerrar(self) -> None:
        self.resumo.falhas = len(self.pncp.falhas)
        self.base.registrar_falhas(agora(), self.pncp.falhas)

    def atualizar_cobertura(self) -> int:
        """Recalcula a tabela de cobertura a partir do que foi efetivamente gravado."""
        linhas = self.base.consultar(
            """
            SELECT c.codigo_ibge, c.ano, c.modalidade_id,
                   COUNT(DISTINCT c.numero_controle_pncp) AS contratacoes,
                   COUNT(i.numero_item)                   AS itens,
                   SUM(CASE WHEN r.numero_item IS NOT NULL THEN 1 ELSE 0 END) AS com_resultado,
                   COALESCE(SUM(DISTINCT c.valor_total_estimado), 0) AS valor_estimado
              FROM contratacao c
              LEFT JOIN item i ON i.numero_controle_pncp = c.numero_controle_pncp
              LEFT JOIN resultado r
                     ON r.numero_controle_pncp = i.numero_controle_pncp
                    AND r.numero_item = i.numero_item
             WHERE c.codigo_ibge IS NOT NULL AND c.ano IS NOT NULL
             GROUP BY c.codigo_ibge, c.ano, c.modalidade_id
            """
        )
        registros = [
            {
                "codigo_ibge": l["codigo_ibge"],
                "ano": l["ano"],
                "modalidade_id": l["modalidade_id"],
                "contratacoes": l["contratacoes"],
                "itens": l["itens"],
                "itens_com_resultado": l["com_resultado"] or 0,
                "valor_estimado": l["valor_estimado"] or 0.0,
                "coletado_em": agora(),
            }
            for l in linhas
        ]
        return self.base.upsert_muitos("cobertura", registros)
