"""Sonda das fontes complementares ao PNCP.

A Fase 0 de 2026-08-24 mediu o limite do PNCP como fonte única: 17 dos 38
municípios-alvo voltaram sem nenhuma contratação, e o caso-âncora — Nova
Castilho, Pregão Presencial 007/2026, com verdade documentada em PDF — não
está lá. Quatro lacunas ficaram abertas: municípios ausentes, número de
licitantes por sessão, enriquecimento de fornecedor e compra prospectiva.

Este módulo não resolve nenhuma delas. Ele **pergunta à rede** se os candidatos
catalogados em ``config/fontes_complementares.yml`` existem, respondem e trazem
o que a lacuna precisa — e escreve o veredito com o código HTTP obtido. É a
mesma disciplina do probe: candidato sem execução não vira conclusão, e
resposta que não chegou é *inconclusiva*, não é *não*.

Roda onde há rede. No ambiente de desenvolvimento todo host relevante está
bloqueado no egress, então o lugar de executar é o GitHub Actions:

    python -m licita fontes
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .config import DADOS, fontes, fontes_complementares, municipios as cfg_municipios
from .http import Cliente, Resposta
from .pncp import _aaaammdd, partes_controle_pncp
from .texto import apenas_digitos

log = logging.getLogger("licita.fontes")

RELATORIO = DADOS / "fontes_complementares.md"
BRUTO = DADOS / "fontes.json"

# Status que dizem "a pergunta não foi respondida", em oposição a "a resposta é
# não". Confundir os dois foi o erro que fez o relatório anterior declarar
# endpoint quebrado quando só havia rate limit.
STATUS_INCONCLUSIVOS = {None, 408, 429, 500, 502, 503, 504}


@dataclass
class Checagem:
    candidato: str
    nome: str
    responde: str
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    status: int | None = None
    registros: int | None = None
    campos: list[str] = field(default_factory=list)
    amostra: str = ""
    erro: str | None = None
    duracao_s: float = 0.0

    @property
    def inconclusiva(self) -> bool:
        return self.status in STATUS_INCONCLUSIVOS

    @property
    def veredito(self) -> str:
        if self.status is not None and 200 <= self.status < 300:
            return "RESPONDE" if self.registros else "RESPONDE VAZIO"
        if self.inconclusiva:
            return "INCONCLUSIVO"
        return "NAO SERVE"


def _resumir(dados: Any) -> tuple[int | None, list[str], str]:
    """Contagem, nomes de campo e amostra legível do que a fonte devolveu."""
    if isinstance(dados, dict) and "trecho" in dados and "bytes" in dados:
        trecho = " ".join(str(dados["trecho"]).split())[:280]
        return (dados["bytes"] or None,
                [f"tipo_conteudo={dados['tipo_conteudo']}"],
                trecho)

    registros: Any = None
    if isinstance(dados, dict):
        for chave in ("data", "gazettes", "result", "cities", "items"):
            if isinstance(dados.get(chave), list):
                registros = dados[chave]
                break
        if registros is None:
            return (1, sorted(dados)[:30], json.dumps(dados, ensure_ascii=False)[:280])
    elif isinstance(dados, list):
        registros = dados
    else:
        return (None, [], str(dados)[:280] if dados is not None else "")

    if not registros:
        return (0, [], "")
    primeiro = registros[0]
    campos = sorted(primeiro)[:30] if isinstance(primeiro, dict) else []
    return (len(registros), campos, json.dumps(primeiro, ensure_ascii=False)[:280])


class SondaFontes:
    def __init__(self) -> None:
        # Perfil `http_sonda`: duas tentativas curtas. São 14 checagens contra
        # hosts que podem nem existir, e um host morto no perfil generoso custa
        # quase 5 minutos. Duas tentativas bastam para separar "não respondeu"
        # de "respondeu não" — e "não respondeu" sai como INCONCLUSIVO, que o
        # relatório manda repetir em vez de tratar como veredito.
        self.http = Cliente(usar_cache=False, perfil="http_sonda")
        self.checagens: list[Checagem] = []
        self.contexto: dict[str, Any] = {}

    # ------------------------------------------------------------ execução

    def _valores(self) -> dict[str, str]:
        cfg = fontes_complementares()
        ancora = cfg_municipios()["caso_ancora"]
        return {
            "ibge_ancora": self._ibge_ancora(),
            "cnpj_ancora": apenas_digitos(ancora["cnpj_orgao"]),
            "ano": str(date.today().year),
            "cnpj_teste": apenas_digitos(cfg.get("cnpj_teste", "")),
        }

    @staticmethod
    def _ibge_ancora() -> str:
        """Código IBGE do caso-âncora, tal como confirmado pela API do IBGE.

        Vem de dados/municipios.json, versionado justamente para que a sonda
        não dependa de resolver o IBGE de novo — e não de literal no código.
        """
        arquivo = DADOS / "municipios.json"
        alvo = cfg_municipios()["caso_ancora"]["municipio"].lower()
        if arquivo.exists():
            for m in json.loads(arquivo.read_text(encoding="utf-8")):
                if str(m.get("nome", "")).lower() == alvo:
                    return str(m["codigo_ibge"])
        log.warning("código IBGE do caso-âncora não resolvido; checagens que "
                    "dependem dele vão sair sem filtro")
        return ""

    @staticmethod
    def _formatar(valor: Any, valores: dict[str, str]) -> Any:
        if isinstance(valor, str):
            try:
                return valor.format(**valores)
            except (KeyError, IndexError):
                return valor
        return valor

    def executar(self) -> None:
        cfg = fontes_complementares()
        valores = self._valores()
        self.contexto = dict(valores)

        for candidato in cfg.get("candidatos", []):
            chave = candidato["chave"]
            log.info("candidato: %s (%s)", candidato["nome"], candidato["lacuna"])
            for checagem in candidato.get("checagens", []):
                if "dinamica" in checagem:
                    self._dinamica(chave, checagem)
                    continue
                url = self._formatar(checagem["url"], valores)
                params = {
                    k: self._formatar(v, valores)
                    for k, v in (checagem.get("params") or {}).items()
                }
                resp = (
                    self.http.obter_bruto(url, params or None)
                    if checagem.get("formato") == "texto"
                    else self.http.obter(url, params or None)
                )
                self._registrar(chave, checagem["nome"], checagem["responde"],
                                url, params, resp)

    def _registrar(self, candidato: str, nome: str, responde: str,
                   url: str, params: dict, resp: Resposta) -> Checagem:
        registros, campos, amostra = _resumir(resp.dados)
        c = Checagem(
            candidato=candidato, nome=nome, responde=responde, url=url,
            params=params, status=resp.status, registros=registros,
            campos=campos, amostra=amostra, erro=resp.erro,
            duracao_s=round(resp.duracao_s, 2),
        )
        self.checagens.append(c)
        log.info("  [%s] %s -> HTTP %s", c.veredito, nome, resp.status)
        return c

    # ------------------------------------------- checagens de alvo dinâmico

    def _alvo_pncp(self) -> tuple[str, int, str] | None:
        """Escolhe uma contratação real da região para exercitar as rotas de detalhe.

        As rotas ``/itens``, ``/resultados`` e ``/arquivos`` nunca foram
        exercitadas: o relatório de 24/08 as marca como "não testadas, porque o
        caso-âncora não foi localizado". Como o caso-âncora não está no PNCP, o
        alvo tem de ser outro — qualquer contratação que a consulta devolva
        para um município prioritário serve, e testar contra dado real vale
        mais que testar contra um número de controle inventado.
        """
        if "alvo_pncp" in self.contexto:
            return self.contexto["alvo_pncp"]

        cfg = fontes()["pncp"]
        url = cfg["consulta_base"] + cfg["contratacoes_publicacao"]
        fim = date.today()
        inicio = fim - timedelta(days=cfg["janela_dias"] - 1)
        prioritarios = [
            m for m in json.loads((DADOS / "municipios.json").read_text(encoding="utf-8"))
            if m.get("prioritario")
        ] if (DADOS / "municipios.json").exists() else []

        for mun in prioritarios:
            for modalidade in (6, 8, 7):
                resp = self.http.obter(url, {
                    "dataInicial": _aaaammdd(inicio), "dataFinal": _aaaammdd(fim),
                    "codigoModalidadeContratacao": modalidade,
                    "codigoMunicipioIbge": mun["codigo_ibge"],
                    "pagina": 1, "tamanhoPagina": 10,
                })
                dados = resp.dados if isinstance(resp.dados, dict) else {}
                for bruto in dados.get("data") or []:
                    partes = partes_controle_pncp(bruto.get("numeroControlePNCP"))
                    if partes:
                        cnpj, sequencial, ano = partes
                        self.contexto["alvo_pncp"] = (cnpj, ano, sequencial)
                        self.contexto["alvo_pncp_descricao"] = (
                            f"{mun['nome']} · {bruto.get('numeroCompra')} · "
                            f"{bruto.get('modalidadeNome')} · "
                            f"{bruto.get('numeroControlePNCP')}"
                        )
                        return self.contexto["alvo_pncp"]

        self.contexto["alvo_pncp"] = None
        return None

    def _dinamica(self, candidato: str, checagem: dict) -> None:
        alvo = self._alvo_pncp()
        if alvo is None:
            self.checagens.append(Checagem(
                candidato=candidato, nome=checagem["nome"],
                responde=checagem["responde"], url="—",
                erro="nenhuma contratação real encontrada para servir de alvo",
            ))
            log.warning("  [INCONCLUSIVO] %s -> sem alvo", checagem["nome"])
            return

        cnpj, ano, sequencial = alvo
        cfg = fontes()["pncp"]
        rotas = {
            "pncp_detalhe_itens": cfg["itens"].format(
                cnpj=cnpj, ano=ano, sequencial=sequencial),
            "pncp_detalhe_resultados": cfg["resultados"].format(
                cnpj=cnpj, ano=ano, sequencial=sequencial, item=1),
            "pncp_detalhe_arquivos": cfg["arquivos"].format(
                cnpj=cnpj, ano=ano, sequencial=sequencial),
        }
        rota = rotas.get(checagem["dinamica"])
        if rota is None:
            return
        url = cfg["detalhe_base"] + rota
        self._registrar(candidato, checagem["nome"], checagem["responde"],
                        url, {}, self.http.obter(url))

    # ------------------------------------------------------------ relatório

    def escrever(self) -> None:
        DADOS.mkdir(parents=True, exist_ok=True)
        BRUTO.write_text(
            json.dumps(
                {
                    "gerado_em": date.today().isoformat(),
                    "contexto": {k: v for k, v in self.contexto.items()
                                 if k != "alvo_pncp"},
                    "checagens": [vars(c) for c in self.checagens],
                },
                ensure_ascii=False, indent=2, default=str,
            ) + "\n",
            encoding="utf-8",
        )
        RELATORIO.write_text(self._markdown(), encoding="utf-8")
        log.info("relatório escrito em %s", RELATORIO)

    def _markdown(self) -> str:
        cfg = fontes_complementares()
        lacunas = cfg.get("lacunas", {})
        por_candidato: dict[str, list[Checagem]] = {}
        for c in self.checagens:
            por_candidato.setdefault(c.candidato, []).append(c)

        linhas = [
            "# Fontes complementares ao PNCP — veredito por execução",
            "",
            f"Executado em {date.today().isoformat()}.",
            "",
            "Cada linha abaixo é uma requisição real, com o código HTTP que ela "
            "devolveu. **Candidato sem execução não vira conclusão** — e "
            "`INCONCLUSIVO` significa que a pergunta não foi respondida "
            "(bloqueio, timeout), não que a resposta seja não.",
            "",
            "## Placar",
            "",
            "| Lacuna | Candidato | Responde | Vazio | Não serve | Inconclusivo |",
            "|---|---|---:|---:|---:|---:|",
        ]

        for candidato in cfg.get("candidatos", []):
            itens = por_candidato.get(candidato["chave"], [])
            conta = {"RESPONDE": 0, "RESPONDE VAZIO": 0,
                     "NAO SERVE": 0, "INCONCLUSIVO": 0}
            for c in itens:
                conta[c.veredito] = conta.get(c.veredito, 0) + 1
            linhas.append(
                f"| {candidato['lacuna']} | {candidato['nome']} | "
                f"{conta['RESPONDE']} | {conta['RESPONDE VAZIO']} | "
                f"{conta['NAO SERVE']} | {conta['INCONCLUSIVO']} |"
            )

        if self.contexto.get("alvo_pncp_descricao"):
            linhas += ["", "> Rotas de detalhe do PNCP exercitadas contra a "
                       f"contratação real: {self.contexto['alvo_pncp_descricao']}"]

        for candidato in cfg.get("candidatos", []):
            itens = por_candidato.get(candidato["chave"], [])
            linhas += [
                "", "---", "",
                f"## {candidato['nome']}",
                "",
                f"**Lacuna que tenta fechar:** {candidato['lacuna']} — "
                f"{lacunas.get(candidato['lacuna'], '').strip()}",
                "",
                (candidato.get("natureza") or "").strip(),
                "",
                "**Documentação consultada:**",
                "",
            ]
            linhas += [f"- {d}" for d in candidato.get("documentacao", [])]
            linhas += ["", "| Checagem | Veredito | HTTP | Registros | Pergunta |",
                       "|---|---|---:|---:|---|"]
            for c in itens:
                n = c.registros if c.registros is not None else "—"
                linhas.append(
                    f"| {c.nome} | **{c.veredito}** | "
                    f"{c.status if c.status is not None else 'sem resposta'} | "
                    f"{n} | {c.responde} |"
                )
            for c in itens:
                if not (c.campos or c.amostra or c.erro):
                    continue
                linhas += ["", f"<details><summary>{c.nome}</summary>", "",
                           f"`{c.url}`", ""]
                if c.params:
                    linhas += [f"Parâmetros: `{c.params}`", ""]
                if c.campos:
                    linhas += ["Campos observados: "
                               + ", ".join(f"`{x}`" for x in c.campos), ""]
                if c.amostra:
                    linhas += ["```", c.amostra, "```", ""]
                if c.erro:
                    linhas += [f"Erro: `{c.erro[:300]}`", ""]
                linhas += ["</details>"]

        linhas += ["", "---", "", "## Como ler este relatório", "",
                   "- **RESPONDE** — a fonte existe, responde e trouxe registro. "
                   "Só aqui cabe decidir integrar.",
                   "- **RESPONDE VAZIO** — a fonte existe e respondeu, mas não "
                   "tem o que se procurou. Para cobertura de município, é "
                   "resposta negativa legítima.",
                   "- **NAO SERVE** — a fonte avaliou a requisição e recusou "
                   "(4xx que não seja 429). Parâmetro errado ou rota inexistente.",
                   "- **INCONCLUSIVO** — bloqueio, timeout ou 5xx. Repetir antes "
                   "de concluir qualquer coisa.", ""]
        return "\n".join(linhas) + "\n"
