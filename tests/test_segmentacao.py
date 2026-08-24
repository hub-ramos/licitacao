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

from licita.segmentar import Classificador, casa, orgao_de_saude  # noqa: E402


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


# ---------------------------------------------------------------------------
# Regressão sobre os objetos REAIS da Fase 0 de 2026-08-24.
#
# A varredura classificou 26 contratações de dispensa, inexigibilidade e
# credenciamento como serviço técnico em saúde. Auditadas uma a uma, 20 não
# eram saúde: munição da Guarda Civil, Libras, LOA, gestão patrimonial,
# EMPRETEC, certificação RPPS, congresso de educação, geoprocessamento de
# engenharia — e três contratos de software, que casaram "cimento" dentro de
# "licenCIMENTO". O tamanho do mercado de serviço técnico em saúde, número que
# decide a segunda linha de negócio do projeto, estava superestimado em 4.3x.
#
# Os textos são os objetos como publicados no PNCP, truncados em 200 caracteres
# pelo probe. Ficam aqui, e não em dados/probe.json, porque aquele arquivo é
# sobrescrito a cada execução e teste não pode depender de arquivo volátil.
# ---------------------------------------------------------------------------

# Os 20 que não são saúde.
NAO_SAO_SAUDE = [
        # Jales
        'Contratação de empresa especializada no fornecimento de licença de '
        'uso de sistema/software para orçamentação eletrônica de peças de '
        'motocicletas, veículos automotivos, maquinas pesadas e implementos',
        # Jales
        'Contratação de empresa especializada na prestação de serviços de '
        'capacitação e treinamento de profissionais no curso In-Company de '
        'Gestão Patrimonial - Reconhecimento, Controle e Desfazimento de '
        'Bens,',
        # Jales
        'O Registro de Preço para eventual aquisição de (munição operacional '
        'de treinamento para uso institucional atendendo às necessidades da '
        'Guarda Civil Municipal), objeto deste Estudo Técnico Preliminar,',
        # Jales
        'Contratação de empresa especializada para prestação de serviços de '
        'capacitação e treinamento de profissionais no SEMINÁRIO EMPRETEC, '
        'por tempo determinado.',
        # Jales
        'Contratação de empresa especializada para prestação de serviços de '
        'capacitação e treinamento de profissionais no 11° Congresso '
        'Internacional de Educação do Noroeste Paulista, com entrega '
        'integral, por',
        # Jales
        'Contratação de empresa para prestação de serviços de capacitação e '
        'treinamento de profissionais no evento Expoeducare 2026- com o tema '
        'Escola e Familia: uma parceria que precisa dar certo, que acontec',
        # Jales
        'Contratação de empresa para prestação de serviços de capacitação e '
        'treinamento de profissionais na Capacitação em Processos '
        'Administrativos (IEG-M), por tempo determinado.',
        # Jales
        'Contratação de empresa para prestação de serviços de capacitação e '
        'treinamento de profissionais no curso de Acompanhamento Familiar em '
        'Grupo no SUAS e Coordenação de CRAS e CREAS, por tempo determinad',
        # Santa Fé do Sul
        'Prestação de serviços, visando ministrar assessoria e capacitação '
        'presencial para servidor lotado junto ao Setor de Contabilidade do '
        'SantaFePrev para fechamento de balanço contábil do exercício de 202',
        # Santa Fé do Sul
        'Contratação de empresa especializada para prestação de serviços de '
        'treinamento e capacitação em Língua Brasileira de Sinais (Libras), a '
        'ser realizado na Casa da Juventude, conforme condições, especifi',
        # Meridiano
        'CONTRATAÇÃO DE SERVIÇOS TÉCNICOS ESPECIALIZADOS DE NATUREZA '
        'PREDOMINANTEMENTE INTELECTUAL PARA A REALIZAÇÃO DE CAPACITAÇÃO E '
        'TREINAMENTO PRESENCIAL SOBRE A ELABORAÇÃO E EXECUÇÃO DA LEI '
        'ORÇAMENTÁRIA AN',
        # Mira Estrela
        '“CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA MINISTRAR CURSO DE '
        'FORMAÇÃO E CAPACITAÇÃO DE PROFISSIONAIS PARA ATUAÇÃO NO CONTEXTO DA '
        'EDUCAÇÃO ESPECIAL INCLUSIVA, CONTEMPLANDO CONHECIMENTOS TEÓRICOS E '
        'PRÁ',
        # Mira Estrela
        '“AQUISIÇÃO DE MATERIAIS ESPORTIVOS destinados à Secretaria Municipal '
        'de Esportes e Lazer do Município de Mira Estrela/SP, com a '
        'finalidade de atender às demandas decorrentes da execução de '
        'programas,',
        # Mira Estrela
        'CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA PRESTAÇÃO DE SERVIÇOS DE '
        'ASSESSORIA, CAPACITAÇÃO, TREINAMENTO, ORIENTAÇÕES E APOIO TÉCNICO '
        'ESPECIALIZADO AOS SERVIDORES DO DEPARTAMENTO DE FINANÇAS DO MUNICÍP',
        # Rubinéia
        'PRESTAÇÃO DE SERVIÇOS TÉCNICOS ESPECIALIZADOS, NA ÁREA DE '
        'ENGENHARIA, ATRAVÉS DO GEOPROCESSAMENTO DE DADOS VETORIAIS, ANÁLISE '
        'E EMISSÃO DE PARECERES TÉCNICOS COM ART ANEXAS, EM SUPORTE TÉCNICO '
        'NA TOMA',
        # Santa Salete
        'CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA FORNECIMENTO DE LICENÇA DE '
        'SISTEMA INFORMATIZADO NA MODALIDADE SAAS (SOFTWARE AS A SERVICE) '
        'PARA BUSCA DE PREÇOS ATRAVÉS DE INTEGRAÇÃO OU DE DADOS INDEXADOS Q',
        # Santa Salete
        'CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA LOCAÇÃO DE SISTEMA '
        'INFORMATIZADO DE GESTÃO E CONTROLE DE FREQUÊNCIA DE SERVIDORES, EM '
        'PLATAFORMA WEB, INCLUINDO IMPLANTAÇÃO, TREINAMENTO, SUPORTE TÉCNICO, '
        'MAN',
        # Santa Salete
        'Contratação de empresa com notória especialização para realização de '
        'curso preparatório de capacitação para obtenção da Cerificação '
        'Profissional RPPS na modalidade a distância para atender as necessid',
        # Santa Salete
        'Inscrição para participação de 01 (um) servidor do Instituto de '
        'Previdência Municipal de Santa Salete – IPREM no evento de '
        'capacitação presencial "RH 360 – 4ª Edição – Encontro Nacional dos '
        'Profission',
        # Santana da Ponte Pensa
        'Contratação de empresa para fornecimento de licenciamento de uso de '
        'softwares nas áreas de recursos humanos/folha de pagamento, pelo '
        'prazo de 12(doze) meses, incluindo os serviços de conversão de dad',
]

# Os 6 que são, com o segmento em que precisam cair.
SAO_SAUDE = [
        # Santa Fé do Sul
        ('servico_saude_digital',
         'Contratação de hospedagem VPS para hospedagem do sistema e-SUS'),
        # Santa Fé do Sul
        ('servico_saude_digital',
         'Contratação de serviço para UPGRADE de disco 50GB para o Sistema '
         'eSUS'),
        # Guarani d'Oeste
        ('servico_vigilancia_saude',
         'CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA PRESTAÇÃO DE SERVIÇOS DE '
         'TERMONEBULIZAÇÃO EM VIAS PÚBLICAS, COM UTILIZAÇÃO DE EQUIPAMENTOS '
         'HOMOLOGADOS E PRODUTOS INSETICIDAS DEVIDAMENTE REGISTRADOS PELA ANV'),
        # Mira Estrela
        ('servico_laboratorial',
         '“Contratação de empresa para prestação de serviços de COLETA DE '
         'EXAMES E ANÁLISES CLÍNICAS LABORATORIAIS em caráter EMERGENCIAL para '
         'Unidade Básica de Saúde de Mira estrela – SP, durante 03 (três) mes'),
        # Rubinéia
        ('servico_saude_assistencial',
         'PRESTAÇÃO DE SERVIÇOS POR TERCEIROS (SERVIÇOS MÉDICOS)'),
        # Santa Salete
        ('servico_vigilancia_saude',
         'CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA PRESTAÇÃO DE SERVIÇOS '
         'VETERINÁRIOS AO SETOR DE VIGILÂNCIA EM SAÚDE E ZOONOSES DO MUNICÍPIO '
         'DE SANTA SALETE/SP'),
]


class MercadoDeSaudeReal(unittest.TestCase):
    """Trava a medição do mercado contra os objetos que já enganaram a taxonomia."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.c = Classificador()

    def _de_saude(self, objeto: str) -> bool:
        cl = self.c.classificar(objeto=objeto)
        return cl.tipo == "servico" and cl.dominio == "saude"

    def test_falsos_positivos_saem_do_mercado_de_saude(self) -> None:
        self.assertEqual(len(NAO_SAO_SAUDE), 20)
        for objeto in NAO_SAO_SAUDE:
            with self.subTest(objeto=objeto[:60]):
                cl = self.c.classificar(objeto=objeto)
                self.assertFalse(
                    self._de_saude(objeto),
                    f"voltou a contar como saúde, em {cl.segmento} pelo termo "
                    f"{cl.termo!r}: {objeto[:90]}",
                )

    def test_verdadeiros_positivos_continuam_no_mercado(self) -> None:
        self.assertEqual(len(SAO_SAUDE), 6)
        for esperado, objeto in SAO_SAUDE:
            with self.subTest(objeto=objeto[:60]):
                cl = self.c.classificar(objeto=objeto)
                self.assertTrue(
                    self._de_saude(objeto),
                    f"saúde de verdade ficou de fora, em {cl.segmento}: {objeto[:90]}",
                )
                self.assertEqual(cl.segmento, esperado, objeto[:90])

    def test_tamanho_do_mercado(self) -> None:
        """O número que a decisão de negócio usa: 6 de 26, não 26."""
        todos = NAO_SAO_SAUDE + [o for _e, o in SAO_SAUDE]
        self.assertEqual(len(todos), 26)
        self.assertEqual(sum(1 for o in todos if self._de_saude(o)), 6)


class FronteiraDePalavra(unittest.TestCase):
    """`cimento` casava dentro de `licenciamento` e mandava software para construção."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.c = Classificador()

    def test_cimento_nao_casa_dentro_de_licenciamento(self) -> None:
        r = self.c.classificar(
            objeto="FORNECIMENTO DE LICENCIAMENTO DE USO DE SOFTWARE DE FOLHA"
        )
        self.assertNotEqual(r.segmento, "madeira_construcao")

    def test_cimento_ainda_casa_como_material(self) -> None:
        r = self.c.classificar(descricao="AQUISICAO DE CIMENTO CP II 50KG")
        self.assertEqual(r.segmento, "madeira_construcao")

    def test_plural_continua_casando(self) -> None:
        self.assertTrue(casa("cimento", "sacos de cimentos diversos"))
        self.assertTrue(casa("exame", "exames laboratoriais"))
        self.assertFalse(casa("cimento", "licenciamento de uso"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
