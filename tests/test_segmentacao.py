"""Classificação dos segmentos de saúde.

A taxonomia prioriza o domínio de saúde pública — vigilância, saúde digital,
análises clínicas e qualidade laboratorial. Estes testes travam o vocabulário
para que uma edição futura em `config/segmentos.yml` não desmonte a
classificação sem que se perceba.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from licita.segmentar import Classificador, orgao_de_saude  # noqa: E402


class Taxonomia(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.c = Classificador()

    def esperar(self, esperado: str, descricao: str = None, objeto: str = None) -> None:
        obtido = self.c.classificar(descricao=descricao, objeto=objeto)
        self.assertEqual(
            obtido.segmento, esperado,
            f"{descricao or objeto!r} caiu em {obtido.segmento!r} (via {obtido.sinal})",
        )

    def test_patogenos_da_vigilancia_sindromica(self) -> None:
        """Agravos de notificação têm que virar oportunidade identificável."""
        for texto in (
            "TESTE RAPIDO PARA INFLUENZA A E B",
            "CAIXA COM 25 TESTES CHIKUNGUNYA IGM/IGG",
            "TESTE RAPIDO DE DENGUE NS1",
            "PAINEL VIRAL RESPIRATORIO - 20 TESTES",
        ):
            self.esperar("testes_rapidos", descricao=texto)

    def test_diagnostico_molecular(self) -> None:
        for texto in (
            "KIT PARA EXTRACAO DE ACIDO NUCLEICO - 96 REACOES",
            "INSUMO PARA RT PCR EM TEMPO REAL",
            "TERMOCICLADOR PARA BIOLOGIA MOLECULAR",
        ):
            self.esperar("diagnostico_molecular", descricao=texto)

    def test_servicos_tecnicos_em_saude(self) -> None:
        casos = {
            "servico_vigilancia_saude":
                "ELABORACAO DE PLANO DE CONTINGENCIA PARA ARBOVIROSES",
            "servico_saude_digital":
                "IMPLANTACAO DE PLATAFORMA DE TELESSAUDE E TELECONSULTORIA",
            "servico_capacitacao_saude":
                "CAPACITACAO DE AGENTES COMUNITARIOS DE SAUDE",
            "servico_indicadores_bi":
                "ESTRUTURACAO DE PAINEL DE INDICADORES DE SAUDE COM GEORREFERENCIAMENTO",
            "servico_qualidade_laboratorial":
                "AUDITORIA DA QUALIDADE DO LABORATORIO MUNICIPAL",
            "servico_laboratorial":
                "CREDENCIAMENTO PARA EXAMES LABORATORIAIS DE ANALISES CLINICAS",
        }
        for esperado, objeto in casos.items():
            self.esperar(esperado, objeto=objeto)

    def test_sistemas_de_informacao_nomeados(self) -> None:
        """Siglas de três letras não entram como palavra-chave; a forma por extenso é a que casa."""
        self.esperar(
            "servico_saude_digital",
            objeto="LICENCA DE SISTEMA DE INFORMACAO LABORATORIAL PARA A REDE",
        )
        self.esperar("servico_saude_digital", objeto="LICENCA DE USO DO REDCAP")

    def test_medicamentos_ficam_bloqueados(self) -> None:
        """Exige responsável técnico farmacêutico; o projeto não habilita este segmento."""
        r = self.c.classificar(descricao="AQUISICAO DE MEDICAMENTOS DA FARMACIA BASICA")
        self.assertEqual(r.segmento, "medicamentos")
        self.assertEqual(r.aderencia, "bloqueado")

    def test_auditoria_contabil_nao_invade_qualidade_laboratorial(self) -> None:
        """Mercado diferente e concorrência diferente: não pode contaminar a linha de saúde."""
        self.esperar(
            "servico_assessoria_geral",
            objeto="CONTRATACAO DE AUDITORIA CONTABIL PARA A PREFEITURA",
        )

    def test_capacitacao_administrativa_nao_conta(self) -> None:
        """O veto de `excluir` evita inflar a linha de capacitação em saúde."""
        r = self.c.classificar(objeto="CAPACITACAO DE SERVIDORES EM LICITACAO")
        self.assertNotEqual(r.segmento, "servico_capacitacao_saude")

    def test_catalogo_tem_precedencia_sobre_descricao(self) -> None:
        """CATMAT preenchido é sinal mais forte que palavra na descrição livre."""
        r = self.c.classificar(descricao="ITEM SEM DESCRICAO UTIL", catmat="6550123")
        self.assertEqual(r.sinal, "catalogo")
        self.assertEqual(r.dominio, "saude")

    def test_palavra_mais_especifica_vence(self) -> None:
        r = self.c.classificar(descricao="CAMARA DE CONSERVACAO DE IMUNOBIOLOGICOS")
        self.assertEqual(r.segmento, "rede_frio_imunizacao")

    def test_fundo_municipal_de_saude_e_orgao_de_saude(self) -> None:
        """Compra de saúde sai no CNPJ do FMS, não no da prefeitura."""
        self.assertTrue(orgao_de_saude("FUNDO MUNICIPAL DE SAUDE DE JALES"))
        self.assertTrue(orgao_de_saude("PREFEITURA", "SECRETARIA MUNICIPAL DE SAUDE"))
        self.assertFalse(orgao_de_saude("PREFEITURA MUNICIPAL DE JALES"))

    def test_todo_segmento_tem_tipo_e_dominio(self) -> None:
        for seg in self.c.segmentos:
            self.assertIn(seg.tipo, {"produto", "servico"}, seg.chave)
            self.assertTrue(seg.dominio, seg.chave)
            self.assertIn(
                seg.aderencia, {"alta", "media", "baixa", "bloqueado"}, seg.chave
            )
            self.assertTrue(seg.palavras or seg.catmat or seg.catser,
                            f"{seg.chave} não tem nenhum sinal de classificação")


if __name__ == "__main__":
    unittest.main(verbosity=2)
