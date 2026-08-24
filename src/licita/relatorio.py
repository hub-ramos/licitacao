"""Geração do relatório de cobertura da Fase 0, em Markdown."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .config import fontes

if TYPE_CHECKING:
    from .probe import Probe

DOMINIOS = fontes()["dominios"]["modalidade"]


def _brl(valor: float | None) -> str:
    if not valor:
        return "—"
    return f"R$ {valor:,.2f}".replace(",", "·").replace(".", ",").replace("·", ".")


def _secao_endpoints(p: "Probe") -> list[str]:
    linhas = [
        "## 1. Endpoints",
        "",
        "| Endpoint | Veredito | HTTP | Registros | Observação |",
        "|---|---|---|---|---|",
    ]
    for s in p.sondas:
        detalhe = s.erro if s.erro else s.observacao
        linhas.append(
            f"| {s.nome} | **{s.veredito}** | {s.status or '—'} "
            f"| {s.registros if s.registros is not None else '—'} | {detalhe or ''} |"
        )
    linhas.append("")

    com_campos = [s for s in p.sondas if s.campos]
    if com_campos:
        linhas += ["<details><summary>Campos observados em cada retorno</summary>", ""]
        for s in com_campos:
            linhas.append(f"**{s.nome}**")
            linhas.append("")
            linhas.append("`" + "`, `".join(s.campos) + "`")
            linhas.append("")
        linhas += ["</details>", ""]

    # Falha e inconclusivo pedem ações diferentes: uma manda corrigir o
    # parâmetro, a outra manda repetir a medição. Somar as duas num número só
    # foi o que fez o relatório de 24/08 anunciar endpoint quebrado quando o que
    # havia era rate limit.
    falhas = [s for s in p.sondas if not s.ok and not s.inconclusivo]
    inconclusivas = [s for s in p.sondas if not s.ok and s.inconclusivo]
    if falhas:
        linhas += [
            "> **Atenção:** "
            f"{len(falhas)} de {len(p.sondas)} endpoints não responderam como esperado. "
            "Os módulos que dependem deles degradam em vez de quebrar, mas a base "
            "ficará incompleta até que sejam corrigidos.",
            "",
        ]
    if inconclusivas:
        linhas += [
            "> **Sem veredito:** "
            f"{len(inconclusivas)} de {len(p.sondas)} sondas não chegaram a ser "
            "respondidas — bloqueio por excesso de requisições ou timeout. Isto "
            "**não** é resposta negativa sobre a fonte: é medição que precisa ser "
            "repetida antes de qualquer conclusão. "
            + "; ".join(s.nome for s in inconclusivas),
            "",
        ]
    return linhas


def _secao_ancora(p: "Probe") -> list[str]:
    a = p.ancora
    verdade = a.get("verdade_conhecida", {})
    linhas = [
        "## 2. Teste de aceitação — Nova Castilho, Pregão Presencial 007/2026",
        "",
        "É o único ponto do projeto com verdade conhecida de forma independente, "
        "extraída dos PDFs oficiais e registrada no handoff. Se o PNCP não contiver "
        "este pregão, a base não serve para pregão presencial de município pequeno — "
        "que é o padrão da região — e o cubo AUDESP do TCE-SP passa de complemento "
        "a peça obrigatória.",
        "",
    ]

    if a.get("encontrado"):
        linhas += [
            "**Resultado: ENCONTRADO.** O PNCP cobre pregão presencial de município pequeno.",
            "",
            "| Campo | Valor no PNCP |",
            "|---|---|",
            f"| Número de controle | `{a.get('numero_controle_pncp', '—')}` |",
            f"| Número da compra | {a.get('numero_compra', '—')} |",
            f"| Modalidade | {a.get('modalidade_nome', '—')} (id {a.get('modalidade_publicada', '—')}) |",
            f"| Casou por | {a.get('casou_por', '—')} |",
            f"| Valor estimado | {_brl(a.get('valor_total_estimado'))} |",
            f"| Valor homologado | {_brl(a.get('valor_total_homologado'))} |",
            "",
            "Confronto com a verdade documentada:",
            "",
            "| Grandeza | Documentado | Conferir no PNCP |",
            "|---|---|---|",
            f"| Preço unitário estimado | R$ {verdade.get('valor_unitario_estimado')}/L | via itens |",
            f"| Preço unitário homologado | R$ {verdade.get('valor_unitario_homologado')}/L | via resultados |",
            f"| Quantidade total | {verdade.get('quantidade_total')} L | via itens |",
            f"| Valor total da ARP | {_brl(verdade.get('valor_total_ata'))} | via atas |",
            f"| Licitantes presentes | {verdade.get('licitantes_presentes')} | **não existe na API** |",
            "",
        ]
    else:
        linhas += [
            "**Resultado: NÃO ENCONTRADO.**",
            "",
            "Duas leituras possíveis, e a diferença entre elas decide o projeto:",
            "",
            "1. O município não publicou este pregão no PNCP. Se for o caso, a "
            "cobertura de presencial é estruturalmente incompleta e o AUDESP "
            "Fase IV vira obrigatório.",
            "2. Publicou, mas sob número, modalidade ou órgão diferentes do "
            "esperado. Confira a tabela de cobertura da seção 3 antes de concluir: "
            "se o município aparece com contratações no período, é este o caso.",
            "",
        ]
    return linhas


def _secao_falhas(p: "Probe") -> list[str]:
    """Falhas de coleta.

    Esta seção existe porque a primeira execução real varreu 37 municípios,
    voltou com zero contratações e o relatório apenas disse "nenhuma contratação
    encontrada" — quando a informação decisiva era que as requisições haviam
    falhado. Coleta vazia e coleta quebrada são coisas diferentes e o relatório
    tem que distingui-las.
    """
    falhas = list(getattr(p.pncp, "falhas", []))
    if not falhas:
        return []

    por_status: dict[object, int] = {}
    for f in falhas:
        por_status[f.status] = por_status.get(f.status, 0) + 1

    linhas = [
        f"> **{len(falhas)} requisições de coleta falharam.** "
        "Cobertura vazia abaixo pode ser efeito disto, não ausência de licitações.",
        "",
        "| HTTP | Ocorrências |",
        "|---|---:|",
    ]
    for status, qtd in sorted(por_status.items(), key=lambda kv: -kv[1]):
        linhas.append(f"| {status if status is not None else 'sem resposta'} | {qtd} |")
    linhas += ["", "Exemplos:", ""]
    for f in falhas[:5]:
        linhas.append(f"- `{f.contexto}` → {f.status}: {str(f.erro or '')[:160]}")
    linhas.append("")
    return linhas


def _secao_cobertura(p: "Probe") -> list[str]:
    linhas = ["## 3. Cobertura por município", ""] + _secao_falhas(p)
    if not p.cobertura:
        return linhas + [
            "Nenhuma contratação encontrada. Se houver falhas acima, a causa é "
            "essa; caso contrário, verifique a seção 1.", ""]

    por_municipio: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "valor": 0.0, "modalidades": defaultdict(int), "anos": set()}
    )
    for reg in p.cobertura:
        alvo = por_municipio[reg["municipio"]]
        alvo["total"] += reg["contratacoes"]
        alvo["valor"] += reg["valor_estimado"] or 0.0
        alvo["modalidades"][reg["modalidade"]] += reg["contratacoes"]
        alvo["anos"].add(reg["ano"])

    linhas += [
        "Contratações que o PNCP efetivamente tem, por município. "
        "Município com zero contratações é sinal de vácuo de **fonte**, não de mercado — "
        "não confundir os dois.",
        "",
        "| Município | Contratações | Anos | Presencial (5,7) | Serviço técnico (8,9,12) | Valor estimado |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for nome, d in sorted(por_municipio.items(), key=lambda kv: -kv[1]["total"]):
        presencial = sum(v for m, v in d["modalidades"].items() if m in (5, 7))
        servico = sum(v for m, v in d["modalidades"].items() if m in (8, 9, 12))
        linhas.append(
            f"| {nome} | {d['total']} | {len(d['anos'])} | {presencial} | {servico} "
            f"| {_brl(d['valor'])} |"
        )
    linhas.append("")

    sem_dados = [m.nome for m in p.municipios if m.nome not in por_municipio]
    if sem_dados:
        linhas += [
            f"**Sem nenhuma contratação no PNCP ({len(sem_dados)}):** "
            + ", ".join(sorted(sem_dados)) + ".",
            "",
            "Estes são os candidatos naturais à camada AUDESP.",
            "",
        ]

    por_modalidade: dict[int, int] = defaultdict(int)
    for reg in p.cobertura:
        por_modalidade[reg["modalidade"]] += reg["contratacoes"]
    linhas += ["### Distribuição por modalidade", "", "| Modalidade | Contratações |", "|---|---:|"]
    for mod, qtd in sorted(por_modalidade.items(), key=lambda kv: -kv[1]):
        linhas.append(f"| {mod} — {DOMINIOS.get(mod, '?')} | {qtd} |")
    linhas.append("")
    return linhas


def _secao_mercado(p: "Probe") -> list[str]:
    linhas = [
        "## 4. Mercado de serviço técnico em saúde",
        "",
        "Contratações em dispensa, inexigibilidade e credenciamento cujo objeto "
        "classifica como serviço do domínio saúde. Dimensiona a segunda linha de "
        "negócio antes de qualquer investimento nela.",
        "",
    ]
    if not p.mercado_servico:
        return linhas + [
            "**Nenhuma contratação encontrada.** Duas leituras: o mercado local é "
            "pequeno demais, ou a taxonomia de `config/segmentos.yml` não está "
            "casando com o vocabulário dos editais da região. Antes de descartar a "
            "linha, revise os objetos brutos em `dados/probe.json`.",
            "",
        ]

    por_municipio: dict[str, int] = defaultdict(int)
    por_segmento: dict[str, int] = defaultdict(int)
    total_valor = 0.0
    for reg in p.mercado_servico:
        por_municipio[reg["municipio"]] += 1
        por_segmento[reg["segmento"]] += 1
        total_valor += float(reg["valor_estimado"] or 0)

    linhas += [
        f"**{len(p.mercado_servico)} contratações** em {len(por_municipio)} municípios, "
        f"somando {_brl(total_valor)} em valor estimado.",
        "",
        "| Segmento | Contratações |",
        "|---|---:|",
    ]
    for seg, qtd in sorted(por_segmento.items(), key=lambda kv: -kv[1]):
        linhas.append(f"| {seg} | {qtd} |")
    linhas += ["", "### Amostra de objetos", ""]
    for reg in p.mercado_servico[:15]:
        linhas.append(f"- **{reg['municipio']}** ({reg['segmento']}): {reg['objeto']}")
    linhas.append("")
    return linhas


def _secao_pendencias(p: "Probe") -> list[str]:
    return [
        "## 5. Pendências que este probe não resolve",
        "",
        "| Pendência | Por quê | Próximo passo |",
        "|---|---|---|",
        "| **Número de licitantes por sessão** | Não existe campo na API do PNCP; "
        "só consta no PDF da ata | Parser best-effort sobre os arquivos, na Fase 3. "
        "Enquanto isso, os proxies (deserção, deságio, HHI) respondem a pergunta de negócio |",
        "| **AUDESP Fase IV (TCE-SP)** | Cubos são arquivos para download, não REST; "
        "exigem inspeção manual do formato | Baixar um cubo de LICITACOES e verificar "
        "se traz contagem de participantes — resolveria a pendência acima de vez |",
        "| **Cobertura de pregão presencial** | Depende do resultado da seção 2 | "
        "Se o caso-âncora falhou, priorizar AUDESP sobre qualquer outra fonte |",
        "",
    ]


def montar(p: "Probe") -> str:
    carimbo = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cabecalho = [
        "# Relatório de cobertura — Fase 0",
        "",
        f"Gerado em {carimbo} · {len(p.municipios)} municípios-alvo",
        "",
        "Este relatório é a primeira coisa a ler no projeto. Ele valida se as fontes "
        "existem e se contêm o que a análise precisa. Nada nas fases seguintes deve "
        "ser considerado confiável antes de as seções 1 e 2 saírem limpas.",
        "",
        "---",
        "",
    ]
    partes = (
        cabecalho
        + _secao_endpoints(p) + ["---", ""]
        + _secao_ancora(p) + ["---", ""]
        + _secao_cobertura(p) + ["---", ""]
        + _secao_mercado(p) + ["---", ""]
        + _secao_pendencias(p)
    )
    return "\n".join(partes)
