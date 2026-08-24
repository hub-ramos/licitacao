"""Regressão do caso-âncora e idempotência da base."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ / "tests"))

from fixtures import (  # noqa: E402
    CONTROLE, ESTIMADO_UNITARIO, FORNECEDOR, HOMOLOGADO_UNITARIO,
    IBGE_NOVA_CASTILHO, PNCPFalso, QUANTIDADE_TOTAL, VALOR_TOTAL_ARP,
)
from licita.coleta import Coletor  # noqa: E402
from licita.db import Base  # noqa: E402
from licita.http import Cliente  # noqa: E402
from licita.ibge import Municipio  # noqa: E402
from licita.metricas import (  # noqa: E402
    Componentes, DESAGIO_SAUDAVEL, calcular, desagio_valido, hhi,
    total_homologado_ajustado, unitario_confiavel,
)
from licita.pncp import link_pncp  # noqa: E402

NOVA_CASTILHO = Municipio(
    codigo_ibge=IBGE_NOVA_CASTILHO, nome="Nova Castilho", uf="SP",
    regiao_imediata="Jales", regiao_intermediaria="São José do Rio Preto",
    motivo_inclusao="regiao_imediata", prioritario=True,
)


class CasoAncora(unittest.TestCase):
    """A base tem que reproduzir os números dos PDFs oficiais."""

    def setUp(self) -> None:
        self.base = Base(":memory:")
        self.pncp = PNCPFalso()
        self.coletor = Coletor(self.base, self.pncp)
        self.coletor.gravar_municipios([NOVA_CASTILHO])
        self.coletor.coletar_historico(
            [NOVA_CASTILHO], date(2026, 1, 1), date(2026, 12, 31)
        )

    def tearDown(self) -> None:
        self.base.fechar()

    def test_contratacao_gravada(self) -> None:
        linha = self.base.consultar(
            "SELECT * FROM contratacao WHERE numero_controle_pncp = ?", (CONTROLE,)
        )
        self.assertEqual(len(linha), 1, "a contratação do caso-âncora deve estar na base")
        c = linha[0]
        self.assertEqual(c["numero_compra"], "007/2026")
        self.assertEqual(c["modalidade_id"], 7)
        self.assertEqual(c["presencial"], 1, "pregão presencial deve ser marcado como presencial")
        self.assertEqual(c["srp"], 1, "é registro de preço")
        self.assertEqual(c["codigo_ibge"], IBGE_NOVA_CASTILHO)

    def test_quantidade_total_confere(self) -> None:
        total = self.base.valor(
            "SELECT SUM(quantidade) FROM item WHERE numero_controle_pncp = ?", (CONTROLE,)
        )
        self.assertEqual(total, QUANTIDADE_TOTAL, "os três itens somam 21.000 litros")

    def test_valor_homologado_reproduz_a_arp(self) -> None:
        total = self.base.valor(
            "SELECT SUM(valor_total_homologado) FROM resultado WHERE numero_controle_pncp = ?",
            (CONTROLE,),
        )
        self.assertAlmostEqual(
            total, VALOR_TOTAL_ARP, places=2,
            msg="21.000 L x R$ 6,92 tem que dar exatamente o valor da ARP",
        )

    def test_desagio_de_1_28_por_cento(self) -> None:
        desagios = [
            l["desagio"] for l in self.base.consultar(
                "SELECT desagio FROM v_item_completo WHERE numero_controle_pncp = ?", (CONTROLE,)
            )
        ]
        self.assertEqual(len(desagios), 3)
        esperado = (ESTIMADO_UNITARIO - HOMOLOGADO_UNITARIO) / ESTIMADO_UNITARIO
        for d in desagios:
            self.assertAlmostEqual(d, esperado, places=6)
        self.assertAlmostEqual(esperado * 100, 1.28, places=2, msg="o deságio documentado é 1,28%")

    def test_item_classificado_como_laticinio(self) -> None:
        segmentos = {
            l["segmento"] for l in self.base.consultar("SELECT DISTINCT segmento FROM item")
        }
        self.assertEqual(segmentos, {"laticinios"})

    def test_fornecedor_unico_registrado(self) -> None:
        fornecedores = self.base.consultar("SELECT * FROM fornecedor")
        self.assertEqual(len(fornecedores), 1, "houve um único licitante")
        self.assertEqual(fornecedores[0]["ni"], FORNECEDOR["ni"])
        self.assertEqual(fornecedores[0]["porte"], "EPP")

    def test_indice_aponta_vacuo_competitivo(self) -> None:
        calcular(self.base)
        m = self.base.consultar(
            "SELECT * FROM metrica_mun_seg_ano WHERE segmento = 'laticinios'"
        )[0]
        self.assertEqual(m["fornecedores_distintos"], 1)
        self.assertAlmostEqual(m["hhi"], 1.0, places=4, msg="fornecedor único concentra tudo")
        self.assertAlmostEqual(m["desagio_medio"], 0.0128, places=4)
        self.assertEqual(m["itens_desertos"], 0)
        self.assertGreater(
            m["indice_oportunidade"], 50,
            "licitante único com deságio de 1,28% tem que pontuar alto no índice",
        )

    def test_agregados_reproduzem_a_arp(self) -> None:
        """Os totais da métrica têm que bater com os PDFs, não só o deságio."""
        calcular(self.base)
        m = self.base.consultar(
            "SELECT * FROM metrica_mun_seg_ano WHERE segmento = 'laticinios'"
        )[0]
        self.assertEqual(m["contratacoes"], 1)
        self.assertEqual(m["itens"], 3)
        self.assertEqual(m["itens_homologados"], 3)
        self.assertEqual(m["itens_fracassados"], 0)
        self.assertAlmostEqual(m["taxa_desercao"], 0.0, places=6)
        self.assertAlmostEqual(m["valor_homologado"], VALOR_TOTAL_ARP, places=2)
        self.assertAlmostEqual(
            m["valor_estimado"], QUANTIDADE_TOTAL * ESTIMADO_UNITARIO, places=2
        )

    def test_indice_reproduz_o_valor_documentado(self) -> None:
        """O índice do caso-âncora é 58,27. Vale a conta inteira, não só "alto".

        Com um ano só na base a recorrência é ``None`` e sai do cálculo, então os
        pesos se renormalizam sobre os três componentes que existem:

            desercao     0/3            = 0,0     × 0,35
            sem_desagio  1 − 0,0128/0,15 = 0,9147 × 0,30
            concentracao HHI             = 1,0    × 0,25
            peso disponível                        = 0,90
            índice = 100 × (0,30×0,9147 + 0,25×1,0) / 0,90 = 58,27

        Se alguém mexer nos pesos, no limiar de deságio saudável ou na
        renormalização, este número muda e o teste avisa.
        """
        calcular(self.base)
        m = self.base.consultar(
            "SELECT * FROM metrica_mun_seg_ano WHERE segmento = 'laticinios'"
        )[0]
        self.assertAlmostEqual(m["indice_oportunidade"], 58.27, places=2)

    def test_arquivos_da_sessao_guardados(self) -> None:
        """A ata em PDF é o insumo do parser de contagem de licitantes (Fase 3)."""
        atas = self.base.consultar(
            "SELECT * FROM arquivo WHERE tipo_documento = 'Ata'"
        )
        self.assertEqual(len(atas), 1)
        self.assertTrue(atas[0]["url"])

    def test_v_vencedor_reproduz_os_tres_itens_do_fornecedor(self) -> None:
        """A aba Vencedores soma isto no cliente — a visão tem que trazer o
        grão certo: um item ganho por linha, com o valor já ajustado."""
        linhas = self.base.consultar(
            "SELECT * FROM v_vencedor WHERE ni_fornecedor = ?", (FORNECEDOR["ni"],)
        )
        self.assertEqual(len(linhas), 3, "três itens, um único fornecedor")
        self.assertEqual({l["numero_controle_pncp"] for l in linhas}, {CONTROLE})
        self.assertAlmostEqual(
            sum(l["valor_total_homologado_ajustado"] for l in linhas),
            VALOR_TOTAL_ARP, places=2,
        )
        for l in linhas:
            self.assertEqual(l["mes"], 7, "data_resultado é 2026-07-29")
            self.assertEqual(l["municipio"], "Nova Castilho")


class ComponentesDoIndice(unittest.TestCase):
    """Componente sem dado não pode virar zero — zero é uma medição, ausência não."""

    def test_ausencia_renormaliza_em_vez_de_pontuar_zero(self) -> None:
        # Só concentração medida, e no pior valor possível. Se a ausência dos
        # outros três virasse zero, o índice cairia para 25 e um mercado
        # capturado apareceria como saudável.
        so_concentracao = Componentes(concentracao=1.0)
        self.assertAlmostEqual(so_concentracao.indice(), 100.0, places=2)

        # Com recorrência ausente, os pesos se dividem entre os três restantes.
        do_ancora = Componentes(
            desercao=0.0,
            sem_desagio=round(1 - 0.0128 / DESAGIO_SAUDAVEL, 4),
            concentracao=1.0,
        )
        self.assertAlmostEqual(do_ancora.indice(), 58.27, places=2)

    def test_sem_nenhum_componente_o_indice_e_nulo(self) -> None:
        self.assertIsNone(Componentes().indice())

    def test_hhi_de_licitante_unico_e_um(self) -> None:
        """O caso-âncora: um fornecedor levando os três itens."""
        self.assertAlmostEqual(hhi([20760.0, 27680.0, 96880.0]), 0.5, places=1)
        self.assertEqual(hhi([VALOR_TOTAL_ARP]), 1.0)
        self.assertIsNone(hhi([]), "sem resultado homologado não há concentração a medir")


class DesagioPublicadoErrado(unittest.TestCase):
    """Defesas que o dado real de Santa Fé do Sul obrigou a existir."""

    def test_total_no_campo_do_unitario_vira_desagio_zero(self) -> None:
        """Caso medido: "Uva Núbia", 2.318 kg a R$ 17,25, e o "unitário"
        homologado publicado foi R$ 39.985,50 — exatamente 2.318 x 17,25.

        Sem tratamento isso vira deságio de -231.700% e arrasta a média do
        segmento para -46.339%. Se o total bate com quantidade x estimado, o
        unitário real é o próprio estimado: deságio zero.
        """
        self.assertEqual(desagio_valido(17.25, 39985.50, 2318), 0.0)

    def test_homologado_absurdo_sai_como_ausencia_de_dado(self) -> None:
        # Acima do dobro do estimado é erro de publicação, não compra cara.
        self.assertIsNone(desagio_valido(10.0, 25.0, 1))
        self.assertIsNone(desagio_valido(10.0, 1000.0, None))

    def test_desagio_negativo_moderado_e_preservado(self) -> None:
        """Comprar acima da estimativa acontece e é informativo — mascarar
        isso esconderia justamente a compra cara."""
        self.assertAlmostEqual(desagio_valido(10.0, 12.0, 1), -0.2, places=6)

    def test_desagio_normal_passa_intacto(self) -> None:
        self.assertAlmostEqual(desagio_valido(7.01, 6.92, 21000), 0.012839, places=5)

    def test_sem_estimativa_nao_ha_desagio(self) -> None:
        for est, hom in ((None, 5.0), (0.0, 5.0), (5.0, None)):
            with self.subTest(est=est, hom=hom):
                self.assertIsNone(desagio_valido(est, hom, 1))


class ValorDoVencedorAjustado(unittest.TestCase):
    """A mesma assinatura de total-no-campo-unitário, aplicada ao ranking de
    vencedores. Caso real: "JOÃO CARLOS DOS SANTOS, 1 item, R$ 92.686.389,00"
    era 2.318 x 39.985,50, onde 39.985,50 já era o total da Uva Núbia."""

    def test_unitario_confiavel_rejeita_total_no_campo_do_unitario(self) -> None:
        self.assertFalse(unitario_confiavel(17.25, 39985.50, 2318))

    def test_unitario_confiavel_rejeita_o_outlier_de_92_milhoes(self) -> None:
        # 2.318 x 39.985,50 = 92.686.389,00: o valor que estourou o ranking.
        self.assertFalse(unitario_confiavel(17.25, 92686389.00, 2318))

    def test_unitario_confiavel_aceita_desagio_normal(self) -> None:
        self.assertTrue(unitario_confiavel(7.01, 6.92, 21000))

    def test_total_ajustado_troca_o_total_bruto_pelo_unitario_publicado(self) -> None:
        # O total bruto publicado (quantidade x unitário-que-era-total) é o que
        # produziria os R$ 92.686.389,00; o total ajustado é o unitário em si.
        self.assertEqual(
            total_homologado_ajustado(17.25, 39985.50, 2318, 92686389.00), 39985.50
        )

    def test_total_ajustado_preserva_o_publicado_quando_confiavel(self) -> None:
        self.assertEqual(
            total_homologado_ajustado(7.01, 6.92, 21000, 145320.00), 145320.00
        )

    def test_total_ajustado_sem_total_publicado_reconstroi_do_unitario(self) -> None:
        self.assertAlmostEqual(
            total_homologado_ajustado(7.01, 6.92, 21000, None), 6.92 * 21000, places=2
        )


class LinkPncp(unittest.TestCase):
    """URL canônica do PNCP, montada a partir do número de controle — presente
    em 100% das contratações, ao contrário de linkSistemaOrigem (8 de 102)."""

    def test_link_do_srp_de_santa_fe_do_sul(self) -> None:
        self.assertEqual(
            link_pncp("45138070000149-1-000762/2026"),
            "https://pncp.gov.br/app/editais/45138070000149/2026/762",
        )

    def test_sem_numero_de_controle_nao_ha_link(self) -> None:
        self.assertIsNone(link_pncp(None))
        self.assertIsNone(link_pncp("numero-invalido"))


class PaginacaoDeItens(unittest.TestCase):
    """`/itens` devolve lista crua, sem envelope — a distribuição de itens por
    contratação secava em 10 porque a coleta não paginava."""

    def test_devolve_mais_de_10_quando_ha_mais_de_10(self) -> None:
        chamadas: list[dict] = []

        class SessaoFalsa:
            def get(self, url, params=None, timeout=None):
                chamadas.append(dict(params or {}))
                pagina = params["pagina"]
                tamanho = params["tamanhoPagina"]
                # Dublê com 23 itens reais, servidos em páginas de `tamanho`.
                total_itens = 23
                inicio = (pagina - 1) * tamanho
                fim = min(inicio + tamanho, total_itens)
                corpo = [{"numeroItem": i + 1} for i in range(inicio, fim)]
                return _RespostaFalsa(corpo)

        http = Cliente(usar_cache=False)
        http._sessao = SessaoFalsa()
        registros = []
        for pagina_registros, _resp in http.paginar(
            "https://pncp.gov.br/api/pncp/v1/orgaos/x/compras/2026/762/itens",
            {"tamanhoPagina": 10},
        ):
            registros.extend(pagina_registros)

        self.assertEqual(len(registros), 23)
        # Três páginas: 10 + 10 + 3, a última mais curta que o tamanho pedido —
        # é essa condição que encerra a paginação numa rota sem `totalPaginas`.
        self.assertEqual(len(chamadas), 3)
        self.assertEqual([c["pagina"] for c in chamadas], [1, 2, 3])


class _RespostaFalsa:
    """Simula ``requests.Response`` o suficiente para ``Cliente.obter``."""

    def __init__(self, corpo) -> None:
        import json as _json
        self.status_code = 200
        self.ok = True
        self._corpo = corpo
        self.content = _json.dumps(corpo).encode("utf-8")
        self.headers: dict = {}
        self.url = "https://pncp.gov.br/api/pncp/v1/fake"

    def json(self):
        return self._corpo


class SemMedidaNaoEZero(unittest.TestCase):
    """Ausência de medida não pode ser lida como medida de ausência."""

    def _base_com(self, situacao: int, modalidade: int = 8) -> Base:
        base = Base(":memory:")
        base.upsert("municipio", {"codigo_ibge": "3546603", "nome": "Santa Fé do Sul",
                                  "uf": "SP", "prioritario": 1})
        base.upsert("contratacao", {
            "numero_controle_pncp": "X-1-1/2026", "codigo_ibge": "3546603",
            "ano": 2026, "modalidade_id": modalidade, "coletado_em": "2026-08-24"})
        base.upsert("item", {
            "numero_controle_pncp": "X-1-1/2026", "numero_item": 1,
            "situacao_item_id": situacao, "segmento": "combustivel",
            "tipo_segmento": "produto", "valor_total_estimado": 1000.0,
            "coletado_em": "2026-08-24"})
        return base

    def test_item_em_andamento_nao_gera_indice(self) -> None:
        """Medido: combustível e laticínios só tinham item em andamento e
        recebiam índice 0,0 — que se lê como 'sem oportunidade'."""
        base = self._base_com(situacao=1)
        try:
            calcular(base)
            linha = base.consultar("SELECT * FROM metrica_mun_seg_ano")[0]
            self.assertIsNone(linha["indice_oportunidade"])
            self.assertIsNone(linha["taxa_desercao"])
        finally:
            base.fechar()

    def test_item_cancelado_nao_gera_indice(self) -> None:
        """Medido: vigilância em saúde, 8 itens anulados/revogados/cancelados.
        Processo que morreu antes do desfecho não diz nada sobre concorrência."""
        base = self._base_com(situacao=3)
        try:
            calcular(base)
            self.assertIsNone(
                base.consultar("SELECT * FROM metrica_mun_seg_ano")[0]["indice_oportunidade"])
        finally:
            base.fechar()

    def test_item_deserto_gera_desercao_total(self) -> None:
        base = self._base_com(situacao=4)
        try:
            calcular(base)
            linha = base.consultar("SELECT * FROM metrica_mun_seg_ano")[0]
            self.assertAlmostEqual(linha["taxa_desercao"], 1.0, places=6)
            self.assertAlmostEqual(linha["indice_oportunidade"], 100.0, places=1)
        finally:
            base.fechar()


class DesagioSoOndeHouveDisputa(unittest.TestCase):
    """Em dispensa o 'estimado' publicado É o contratado: deságio zero por
    construção. Medido: 271 de 275 itens de dispensa com deságio exato zero.

    Creditar isso como vácuo competitivo faria o índice medir quanto o
    município usa dispensa, não onde há pouca concorrência.
    """

    def _com_modalidade(self, modalidade: int) -> dict:
        base = Base(":memory:")
        try:
            base.upsert("municipio", {"codigo_ibge": "3546603", "nome": "Santa Fé do Sul",
                                      "uf": "SP", "prioritario": 1})
            base.upsert("contratacao", {
                "numero_controle_pncp": "X-1-1/2026", "codigo_ibge": "3546603",
                "ano": 2026, "modalidade_id": modalidade, "coletado_em": "2026-08-24"})
            base.upsert("item", {
                "numero_controle_pncp": "X-1-1/2026", "numero_item": 1,
                "situacao_item_id": 2, "segmento": "papelaria_expediente",
                "tipo_segmento": "produto", "quantidade": 100.0,
                "valor_unitario_estimado": 10.0, "valor_total_estimado": 1000.0,
                "coletado_em": "2026-08-24"})
            base.upsert("fornecedor", {"ni": "00000000000191", "nome": "F", "porte": "ME"})
            base.upsert("resultado", {
                "numero_controle_pncp": "X-1-1/2026", "numero_item": 1,
                "sequencial_resultado": 1, "ni_fornecedor": "00000000000191",
                "valor_unitario_homologado": 10.0,     # deságio zero
                "valor_total_homologado": 1000.0, "coletado_em": "2026-08-24"})
            calcular(base)
            return base.consultar("SELECT * FROM metrica_mun_seg_ano")[0]
        finally:
            base.fechar()

    def test_dispensa_nao_pontua_por_ausencia_de_desagio(self) -> None:
        linha = self._com_modalidade(8)
        self.assertIsNone(linha["desagio_medio"],
                          "dispensa não tem deságio a medir")
        # Sobram deserção (0) e concentração (1,0): 100 x 0,25/0,60 = 41,67
        self.assertAlmostEqual(linha["indice_oportunidade"], 41.67, places=1)

    def test_pregao_com_desagio_zero_pontua(self) -> None:
        """No pregão, deságio zero é o sinal que o projeto procura: houve
        disputa possível e o preço não caiu."""
        linha = self._com_modalidade(6)
        self.assertAlmostEqual(linha["desagio_medio"], 0.0, places=6)
        self.assertGreater(linha["indice_oportunidade"],
                           self._com_modalidade(8)["indice_oportunidade"])


class MigracaoDeColunaAditiva(unittest.TestCase):
    """Base já existente, criada antes de `link_pncp` existir, tem que ganhar
    a coluna sem perder dado — `CREATE TABLE IF NOT EXISTS` não altera tabela
    já criada, e a base de Santa Fé do Sul já está commitada sem ela."""

    def test_base_antiga_ganha_a_coluna_sem_perder_linha(self) -> None:
        import sqlite3
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "antiga.db"
            # Simula o schema anterior: a tabela `contratacao` real, mas sem a
            # coluna `link_pncp` — como a base commitada de Santa Fé do Sul.
            con = sqlite3.connect(str(caminho))
            con.execute("""
                CREATE TABLE contratacao (
                    numero_controle_pncp        TEXT PRIMARY KEY,
                    cnpj_orgao                  TEXT,
                    codigo_ibge                 TEXT,
                    ano                         INTEGER,
                    sequencial                  TEXT,
                    numero_compra               TEXT,
                    processo                    TEXT,
                    modalidade_id               INTEGER,
                    modalidade_nome             TEXT,
                    presencial                  INTEGER NOT NULL DEFAULT 0,
                    modo_disputa_id             INTEGER,
                    modo_disputa_nome           TEXT,
                    situacao_id                 INTEGER,
                    situacao_nome               TEXT,
                    srp                         INTEGER NOT NULL DEFAULT 0,
                    objeto                      TEXT,
                    valor_total_estimado        REAL,
                    valor_total_homologado      REAL,
                    data_publicacao             TEXT,
                    data_abertura_proposta      TEXT,
                    data_encerramento_proposta  TEXT,
                    unidade_nome                TEXT,
                    unidade_codigo               TEXT,
                    orgao_de_saude              INTEGER NOT NULL DEFAULT 0,
                    amparo_legal                TEXT,
                    link_sistema_origem         TEXT,
                    coletado_em                 TEXT NOT NULL
                )
            """)
            valores = {"numero_controle_pncp": "X-1-1/2026", "codigo_ibge": "3546603",
                       "ano": 2026, "coletado_em": "2026-08-24"}
            con.execute(
                f"INSERT INTO contratacao ({','.join(valores)}) "
                f"VALUES ({','.join('?' * len(valores))})",
                list(valores.values()),
            )
            con.commit()
            con.close()

            base = Base(caminho)
            try:
                cols = {r["name"] for r in base.con.execute("PRAGMA table_info(contratacao)")}
                self.assertIn("link_pncp", cols)
                self.assertEqual(base.contar("contratacao"), 1)
            finally:
                base.fechar()


class Idempotencia(unittest.TestCase):
    """Rodar a coleta duas vezes não pode duplicar linha nem mudar métrica."""

    def test_coleta_repetida_nao_duplica(self) -> None:
        base = Base(":memory:")
        try:
            for _ in range(2):
                coletor = Coletor(base, PNCPFalso())
                coletor.gravar_municipios([NOVA_CASTILHO])
                coletor.coletar_historico(
                    [NOVA_CASTILHO], date(2026, 1, 1), date(2026, 12, 31)
                )
            self.assertEqual(base.contar("contratacao"), 1)
            self.assertEqual(base.contar("item"), 3)
            self.assertEqual(base.contar("resultado"), 3)
            self.assertEqual(base.contar("municipio"), 1)
            self.assertEqual(base.contar("arquivo"), 2)

            primeiro = calcular(base)
            segundo = calcular(base)
            self.assertEqual(primeiro, segundo, "recalcular métricas deve ser estável")
            self.assertEqual(base.contar("metrica_mun_seg_ano"), segundo)
        finally:
            base.fechar()


class Exports(unittest.TestCase):
    def test_painel_e_csv_saem_sem_erro(self) -> None:
        import tempfile
        from licita.exportar import para_csv, para_painel

        base = Base(":memory:")
        try:
            coletor = Coletor(base, PNCPFalso())
            coletor.gravar_municipios([NOVA_CASTILHO])
            coletor.coletar_historico([NOVA_CASTILHO], date(2026, 1, 1), date(2026, 12, 31))
            calcular(base)

            with tempfile.TemporaryDirectory() as tmp:
                destino = Path(tmp)
                escritos = para_csv(base, destino)
                self.assertTrue(escritos)
                itens = (destino / "itens.csv").read_text(encoding="utf-8-sig")
                self.assertIn("laticinios", itens)
                self.assertIn("Nova Castilho", itens)

                painel = para_painel(base, destino / "painel.html")
                html = painel.read_text(encoding="utf-8")
                self.assertNotIn("/*__DADOS__*/null", html, "os dados devem ter sido injetados")
                self.assertIn(FORNECEDOR["nome"], html)
        finally:
            base.fechar()


if __name__ == "__main__":
    unittest.main(verbosity=2)
