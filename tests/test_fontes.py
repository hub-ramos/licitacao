"""Sonda de fontes complementares: catálogo bem-formado e vereditos corretos.

Estes testes rodam sem rede. Não verificam se uma fonte existe — isso só a
execução em ambiente com acesso responde. Verificam que o catálogo está
íntegro e que a sonda não confunde "não respondeu" com "respondeu não", que foi
o erro que fez o relatório de 2026-08-24 declarar cobertura zero onde havia
103 bloqueios por excesso de requisições.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from licita.config import fontes, fontes_complementares  # noqa: E402
from licita.fontes_extra import Checagem, SondaFontes, _resumir  # noqa: E402


class Catalogo(unittest.TestCase):
    """O catálogo é a parte auditável: cada pergunta tem que ter fonte citada."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = fontes_complementares()

    def test_toda_lacuna_tem_ao_menos_um_candidato(self) -> None:
        declaradas = set(self.cfg["lacunas"])
        cobertas = {c["lacuna"] for c in self.cfg["candidatos"]}
        self.assertEqual(declaradas, cobertas,
                         "lacuna sem candidato é lacuna que ninguém vai medir")

    def test_todo_candidato_cita_a_documentacao(self) -> None:
        for c in self.cfg["candidatos"]:
            with self.subTest(candidato=c["chave"]):
                docs = c.get("documentacao") or []
                self.assertTrue(docs, f"{c['chave']} não cita fonte de documentação")
                for d in docs:
                    self.assertTrue(str(d).startswith("http"), d)

    def test_toda_checagem_declara_o_que_pergunta(self) -> None:
        for c in self.cfg["candidatos"]:
            for chk in c["checagens"]:
                with self.subTest(checagem=chk["nome"]):
                    self.assertTrue(chk.get("responde", "").strip())
                    # Ou tem URL própria, ou é resolvida em tempo de execução.
                    self.assertTrue(chk.get("url") or chk.get("dinamica"))

    def test_perfil_de_sonda_existe_e_e_curto(self) -> None:
        """Orçamento longo contra host morto transforma a sonda numa hora parada."""
        perfil = fontes()["http_sonda"]
        self.assertLessEqual(perfil["max_tentativas"], 3)
        self.assertLessEqual(perfil["timeout_s"], 30)


class Vereditos(unittest.TestCase):
    def test_bloqueio_e_inconclusivo_nao_recusa(self) -> None:
        for status in (429, 503, None):
            with self.subTest(status=status):
                c = Checagem("x", "n", "r", "u", status=status)
                self.assertEqual(c.veredito, "INCONCLUSIVO")

    def test_recusa_da_api_e_veredito_negativo(self) -> None:
        for status in (400, 404, 422):
            with self.subTest(status=status):
                c = Checagem("x", "n", "r", "u", status=status)
                self.assertEqual(c.veredito, "NAO SERVE")

    def test_resposta_vazia_e_diferente_de_resposta_com_dado(self) -> None:
        self.assertEqual(Checagem("x", "n", "r", "u", status=200, registros=0).veredito,
                         "RESPONDE VAZIO")
        self.assertEqual(Checagem("x", "n", "r", "u", status=200, registros=3).veredito,
                         "RESPONDE")


class Resumo(unittest.TestCase):
    """`_resumir` precisa entender os envelopes das APIs candidatas."""

    def test_envelope_do_pncp(self) -> None:
        n, campos, _ = _resumir({"data": [{"b": 2, "a": 1}], "totalRegistros": 1})
        self.assertEqual((n, campos), (1, ["a", "b"]))

    def test_envelope_do_querido_diario(self) -> None:
        n, campos, _ = _resumir({"total_gazettes": 4, "gazettes": [{"date": "x"}]})
        self.assertEqual((n, campos), (1, ["date"]))

    def test_lista_crua(self) -> None:
        n, campos, _ = _resumir([{"numeroItem": 1}])
        self.assertEqual((n, campos), (1, ["numeroItem"]))

    def test_objeto_unico_sem_envelope(self) -> None:
        """BrasilAPI devolve o CNPJ direto, sem envelope nem lista."""
        n, campos, _ = _resumir({"cnpj": "00", "cnae_fiscal": 1, "porte": "x"})
        self.assertEqual(n, 1)
        self.assertIn("cnae_fiscal", campos)

    def test_conteudo_nao_json(self) -> None:
        n, campos, amostra = _resumir(
            {"tipo_conteudo": "text/yaml", "bytes": 1234, "trecho": "openapi: 3.0.0"}
        )
        self.assertEqual(n, 1234)
        self.assertIn("tipo_conteudo=text/yaml", campos)
        self.assertIn("openapi", amostra)

    def test_envelope_ckan_do_tesouro(self) -> None:
        """CKAN aninha os recursos; a URL do XLSX da CAPAG está em result.resources."""
        n, campos, amostra = _resumir({
            "success": True,
            "result": {"name": "capag-municipios", "resources": [
                {"format": "XLSX", "url": "https://x/capag.xlsx",
                 "last_modified": "2026-03-01"},
            ]},
        })
        self.assertEqual(n, 1)
        self.assertIn("last_modified", campos)
        self.assertIn("XLSX", amostra)

    def test_vazio_nao_vira_none(self) -> None:
        self.assertEqual(_resumir({"data": []})[0], 0)


class RelatorioSemRede(unittest.TestCase):
    def test_markdown_separa_os_quatro_vereditos(self) -> None:
        s = SondaFontes()
        s.checagens = [
            Checagem("querido_diario", "a", "?", "u", status=200, registros=2),
            Checagem("querido_diario", "b", "?", "u", status=200, registros=0),
            Checagem("tce_sp_audesp", "c", "?", "u", status=404),
            Checagem("tce_sp_audesp", "d", "?", "u", status=429),
        ]
        md = s._markdown()
        for veredito in ("RESPONDE", "RESPONDE VAZIO", "NAO SERVE", "INCONCLUSIVO"):
            self.assertIn(veredito, md)
        self.assertIn("Candidato sem execução não vira conclusão", md)


class RecorteDeColeta(unittest.TestCase):
    """Filtro de município: existe para tornar possível coleta de calibração."""

    @classmethod
    def setUpClass(cls) -> None:
        from licita.ibge import Municipio
        cls.alvos = [
            Municipio("3546603", "Santa Fé do Sul", "SP", "Santa Fé do Sul",
                      "São José do Rio Preto", "regiao_imediata", True),
            Municipio("3525300", "Jales", "SP", "Jales",
                      "São José do Rio Preto", "regiao_imediata", True),
            Municipio("3532868", "Nova Castilho", "SP", "Araçatuba",
                      "Araçatuba", "extra", True),
        ]

    def test_sem_filtro_devolve_tudo(self) -> None:
        from licita.__main__ import _filtrar
        self.assertEqual(len(_filtrar(self.alvos, None)), 3)
        self.assertEqual(len(_filtrar(self.alvos, "")), 3)

    def test_filtra_por_nome_ignorando_acento_e_caixa(self) -> None:
        from licita.__main__ import _filtrar
        for escrito in ("Santa Fé do Sul", "santa fe do sul", "SANTA FE DO SUL"):
            with self.subTest(escrito=escrito):
                self.assertEqual([m.nome for m in _filtrar(self.alvos, escrito)],
                                 ["Santa Fé do Sul"])

    def test_filtra_por_codigo_ibge(self) -> None:
        from licita.__main__ import _filtrar
        self.assertEqual([m.nome for m in _filtrar(self.alvos, "3525300")], ["Jales"])

    def test_aceita_lista(self) -> None:
        from licita.__main__ import _filtrar
        self.assertEqual([m.nome for m in _filtrar(self.alvos, "Jales, Nova Castilho")],
                         ["Jales", "Nova Castilho"])

    def test_nome_errado_para_a_coleta(self) -> None:
        """Filtro vazio por erro de digitação é indistinguível de município sem
        licitação — e essa confusão já custou uma rodada a este projeto."""
        from licita.__main__ import _filtrar
        with self.assertRaises(SystemExit) as ctx:
            _filtrar(self.alvos, "Santa Fe do Sul S/A")
        self.assertIn("não encontrado", str(ctx.exception))
        self.assertIn("Jales", str(ctx.exception), "a mensagem lista os conhecidos")


if __name__ == "__main__":
    unittest.main(verbosity=2)
