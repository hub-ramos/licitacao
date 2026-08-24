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
from licita.ibge import Municipio  # noqa: E402
from licita.metricas import Componentes, DESAGIO_SAUDAVEL, calcular, hhi  # noqa: E402

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
