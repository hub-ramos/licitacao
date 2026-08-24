"""Métricas de concorrência e Índice de Oportunidade.

O PNCP não publica quantos licitantes compareceram a uma sessão — esse número só
existe no PDF da ata. O índice aqui substitui essa contagem por sinais que a API
entrega e que medem a mesma coisa:

* **Deserção** — item deserto (ninguém apareceu) ou fracassado (todos
  inabilitados). É prova literal de concorrência zero, e o sinal mais forte.
* **Ausência de deságio** — quanto o preço homologado caiu ante a estimativa.
  Em Nova Castilho o leite caiu 1,28%: assinatura de licitante único. Disputa
  real derruba preço; disputa inexistente não derruba.
* **Concentração (HHI)** — um único CNPJ levando tudo indica mercado capturado.
* **Recorrência** — item que se repete ano após ano é previsível, e previsível
  significa que dá para se preparar com antecedência.

Componentes sem dado não são chutados: os pesos são renormalizados sobre os
componentes disponíveis. Um município sem nenhum resultado homologado não recebe
índice inflado por um deságio que ninguém mediu.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import fontes
from .db import Base, agora

log = logging.getLogger("licita.metricas")

# Deságio a partir do qual se considera que houve disputa de verdade. Acima disso
# o componente "ausência de deságio" zera. Calibrado no caso-âncora: 1,28% com um
# único licitante; um pregão disputado costuma passar de 15%.
DESAGIO_SAUDAVEL = 0.15

PESOS = {
    "desercao": 0.35,
    "sem_desagio": 0.30,
    "concentracao": 0.25,
    "recorrencia": 0.10,
}

SITUACAO_DESERTO = 4
SITUACAO_FRACASSADO = 5


def total_no_campo_unitario(estimado: float | None, homologado: float | None,
                            quantidade: float | None) -> bool:
    """Assinatura do erro de publicação mais comum: ``homologado ≈ qtd × estimado``.

    Caso real, medido em Santa Fé do Sul: "Uva Núbia", 2.318 kg, estimado
    R$ 17,25/kg e "unitário homologado" de R$ 39.985,50 — que é exatamente
    2.318 × 17,25. O órgão publicou o valor total no campo do unitário.

    O reconhecimento é conservador de propósito: exige quantidade maior que 1
    (com quantidade 1 total e unitário coincidem legitimamente) e tolerância de
    um centavo, porque o total costuma vir arredondado.
    """
    if not estimado or estimado <= 0 or homologado is None:
        return False
    if not quantidade or quantidade <= 1:
        return False
    return abs(homologado - estimado * quantidade) < 0.01


def unitario_confiavel(estimado: float | None, homologado: float | None,
                       quantidade: float | None) -> bool:
    """Diz se ``homologado`` pode ser lido como preço unitário de verdade.

    Duas recusas, ambas medidas no dado real:

    * **Total no campo unitário** — ver :func:`total_no_campo_unitario`.
    * **Absurdo sem assinatura** — homologado acima do dobro do estimado é erro
      de publicação, não compra cara.

    Existe separada de :func:`desagio_valido` porque o mesmo juízo vale para o
    valor do vencedor: multiplicar um "unitário" que já é total pela quantidade
    produziu, no ranking de fornecedores, um item de R$ 92.686.389,00
    (= 2.318 × 39.985,50) para uma compra de R$ 39.985,50.
    """
    if not estimado or estimado <= 0 or homologado is None:
        return False
    if total_no_campo_unitario(estimado, homologado, quantidade):
        return False
    return (estimado - homologado) / estimado >= -1.0


def desagio_valido(estimado: float | None, homologado: float | None,
                   quantidade: float | None) -> float | None:
    """Deságio unitário, ou ``None`` quando o publicado não é comparável.

    Quando a assinatura de total-no-campo-unitário bate, o unitário real é o
    próprio estimado e o deságio é zero — não ``None``: sabe-se que não houve
    desconto, o que é justamente o sinal que o projeto procura. Sem tratamento
    isso viraria deságio de −231.700% e arrastaria a média do segmento para
    −46.339%.

    Deságio negativo moderado é preservado: comprar acima da estimativa acontece
    e é informativo.
    """
    if not estimado or estimado <= 0 or homologado is None:
        return None
    if total_no_campo_unitario(estimado, homologado, quantidade):
        return 0.0
    if not unitario_confiavel(estimado, homologado, quantidade):
        return None
    return (estimado - homologado) / estimado


def total_homologado_ajustado(estimado: float | None, unitario_homologado: float | None,
                              quantidade: float | None,
                              total_publicado: float | None) -> float | None:
    """Valor total do item corrigido, quando o publicado é reconhecidamente errado.

    O órgão que publica o total no campo do unitário publica, junto, um
    ``valorTotalHomologado`` de quantidade × aquele número — que é a quantidade
    ao quadrado vezes o preço. É esse valor que colocou "1 item, R$ 92.686.389,00"
    no topo do ranking de vencedores. Quando a assinatura bate, o total correto é
    o próprio campo do unitário.

    O valor cru continua gravado ao lado, intacto: o ajuste só é auditável se o
    publicado puder ser conferido contra ele.
    """
    if total_no_campo_unitario(estimado, unitario_homologado, quantidade):
        return unitario_homologado
    if total_publicado is not None:
        return total_publicado
    if unitario_homologado is None or not quantidade:
        return None
    # Sem total publicado, reconstruir só quando o unitário resiste ao exame.
    if not unitario_confiavel(estimado, unitario_homologado, quantidade):
        return None
    return round(unitario_homologado * quantidade, 2)


@dataclass
class Componentes:
    """Parcelas do índice. ``None`` significa 'sem dado', não 'zero'."""

    desercao: float | None = None
    sem_desagio: float | None = None
    concentracao: float | None = None
    recorrencia: float | None = None

    def indice(self) -> float | None:
        """Média ponderada sobre os componentes disponíveis, em escala 0..100."""
        disponiveis = {
            nome: valor
            for nome, valor in vars(self).items()
            if valor is not None
        }
        if not disponiveis:
            return None
        peso_total = sum(PESOS[nome] for nome in disponiveis)
        if peso_total <= 0:
            return None
        soma = sum(PESOS[nome] * valor for nome, valor in disponiveis.items())
        return round(100 * soma / peso_total, 2)


def hhi(valores: list[float]) -> float | None:
    """Índice Herfindahl-Hirschman normalizado 0..1 sobre participações.

    1,0 = um único fornecedor leva tudo. Valores baixos = mercado pulverizado.
    """
    positivos = [v for v in valores if v and v > 0]
    total = sum(positivos)
    if not positivos or total <= 0:
        return None
    return round(sum((v / total) ** 2 for v in positivos), 4)


def _recorrencia(anos_do_segmento: int, anos_na_base: int) -> float | None:
    """Fração dos anos observados em que o município comprou aquele segmento."""
    if anos_na_base <= 1:
        return None          # com um ano só não há como falar em recorrência
    return round(min(anos_do_segmento / anos_na_base, 1.0), 4)


def calcular(base: Base) -> int:
    """Recalcula ``metrica_mun_seg_ano`` inteira a partir dos fatos.

    Recálculo completo, não incremental: é barato no volume desta base e elimina
    a classe de bug em que uma métrica antiga sobrevive a uma correção de dado.
    """
    anos = [
        linha["ano"]
        for linha in base.consultar(
            "SELECT DISTINCT ano FROM contratacao WHERE ano IS NOT NULL ORDER BY ano"
        )
    ]
    anos_na_base = len(anos)

    # Em quantos anos distintos cada (município, segmento) apareceu.
    presenca = {
        (l["codigo_ibge"], l["segmento"]): l["anos"]
        for l in base.consultar(
            """
            SELECT c.codigo_ibge, i.segmento, COUNT(DISTINCT c.ano) AS anos
              FROM item i
              JOIN contratacao c ON c.numero_controle_pncp = i.numero_controle_pncp
             WHERE c.codigo_ibge IS NOT NULL AND i.segmento IS NOT NULL
             GROUP BY c.codigo_ibge, i.segmento
            """
        )
    }

    # A lista vem de config/fontes.yml; interpolar inteiros validados é seguro e
    # evita um IN de tamanho variável em parâmetro ligado.
    concluidas = ",".join(str(int(x)) for x in
                          fontes().get("situacoes_item_concluidas", [2, 4, 5]))
    agregados = base.consultar(
        """
        SELECT
            c.codigo_ibge,
            i.segmento,
            c.ano,
            i.tipo_segmento,
            COUNT(DISTINCT c.numero_controle_pncp) AS contratacoes,
            COUNT(DISTINCT i.numero_controle_pncp || '#' || i.numero_item) AS itens,
            SUM(CASE WHEN i.situacao_item_id = 2 THEN 1 ELSE 0 END) AS homologados,
            SUM(CASE WHEN i.situacao_item_id = ? THEN 1 ELSE 0 END) AS desertos,
            SUM(CASE WHEN i.situacao_item_id = ? THEN 1 ELSE 0 END) AS fracassados,
            SUM(CASE WHEN i.situacao_item_id IN ({concluidas}) THEN 1 ELSE 0 END) AS concluidos,
            COALESCE(SUM(i.valor_total_estimado), 0) AS valor_estimado
          FROM item i
          JOIN contratacao c ON c.numero_controle_pncp = i.numero_controle_pncp
         WHERE c.codigo_ibge IS NOT NULL AND c.ano IS NOT NULL AND i.segmento IS NOT NULL
         GROUP BY c.codigo_ibge, i.segmento, c.ano, i.tipo_segmento
        """.format(concluidas=concluidas),
        (SITUACAO_DESERTO, SITUACAO_FRACASSADO),
    )

    registros: list[dict] = []
    for linha in agregados:
        chave = (linha["codigo_ibge"], linha["segmento"], linha["ano"])
        detalhe = _detalhar(base, *chave)

        itens = linha["itens"] or 0
        desertos = linha["desertos"] or 0
        fracassados = linha["fracassados"] or 0

        comp = Componentes()
        # Deserção só se mede sobre item com desfecho. Item "Em Andamento" não é
        # prova de que ninguém apareceu — contá-lo como não-deserto dava
        # deserção 0,0 e, sem os outros componentes, índice 0,0, que se lê como
        # "sem oportunidade" quando significa "ainda sem medida".
        concluidos = linha["concluidos"] or 0
        if concluidos:
            comp.desercao = round((desertos + fracassados) / concluidos, 4)
        if detalhe["desagio_medio"] is not None:
            comp.sem_desagio = round(
                1 - min(max(detalhe["desagio_medio"], 0.0) / DESAGIO_SAUDAVEL, 1.0), 4
            )
        comp.concentracao = detalhe["hhi"]
        comp.recorrencia = _recorrencia(
            presenca.get((linha["codigo_ibge"], linha["segmento"]), 0), anos_na_base
        )

        registros.append({
            "codigo_ibge": linha["codigo_ibge"],
            "segmento": linha["segmento"],
            "ano": linha["ano"],
            "tipo_segmento": linha["tipo_segmento"],
            "contratacoes": linha["contratacoes"] or 0,
            "itens": itens,
            "itens_homologados": linha["homologados"] or 0,
            "itens_desertos": desertos,
            "itens_fracassados": fracassados,
            "valor_estimado": linha["valor_estimado"] or 0.0,
            "valor_homologado": detalhe["valor_homologado"],
            "desagio_medio": detalhe["desagio_medio"],
            "taxa_desercao": comp.desercao,
            "fornecedores_distintos": detalhe["fornecedores"],
            "hhi": detalhe["hhi"],
            "indice_oportunidade": comp.indice(),
            "calculado_em": agora(),
        })

    base.con.execute("DELETE FROM metrica_mun_seg_ano")
    gravados = base.upsert_muitos("metrica_mun_seg_ano", registros)
    log.info("métricas recalculadas: %d linhas", gravados)
    return gravados


def _detalhar(base: Base, codigo_ibge: str, segmento: str, ano: int) -> dict:
    """Deságio médio, valor homologado, fornecedores distintos e HHI de um recorte."""
    com_disputa = set(fontes().get("modalidades_com_disputa", []))
    linhas = base.consultar(
        """
        SELECT r.ni_fornecedor,
               r.valor_total_homologado,
               i.valor_unitario_estimado,
               r.valor_unitario_homologado,
               i.quantidade,
               c.modalidade_id
          FROM item i
          JOIN contratacao c ON c.numero_controle_pncp = i.numero_controle_pncp
          JOIN resultado r
               ON r.numero_controle_pncp = i.numero_controle_pncp
              AND r.numero_item = i.numero_item
         WHERE c.codigo_ibge = ? AND i.segmento = ? AND c.ano = ?
        """,
        (codigo_ibge, segmento, ano),
    )

    desagios: list[float] = []
    por_fornecedor: dict[str, float] = {}
    total_homologado = 0.0

    for l in linhas:
        # Deságio só entra no índice onde houve disputa de preço. Em dispensa e
        # inexigibilidade o "estimado" publicado É o contratado, então o deságio
        # é zero por construção — creditar isso como vácuo competitivo faria o
        # índice medir quanto o município usa dispensa, não onde há vácuo.
        if l["modalidade_id"] in com_disputa:
            d = desagio_valido(l["valor_unitario_estimado"],
                               l["valor_unitario_homologado"], l["quantidade"])
            if d is not None:
                desagios.append(d)

        valor = l["valor_total_homologado"] or 0.0
        total_homologado += valor
        if l["ni_fornecedor"]:
            por_fornecedor[l["ni_fornecedor"]] = por_fornecedor.get(l["ni_fornecedor"], 0.0) + valor

    return {
        "desagio_medio": round(sum(desagios) / len(desagios), 4) if desagios else None,
        "valor_homologado": round(total_homologado, 2),
        "fornecedores": len(por_fornecedor),
        "hhi": hhi(list(por_fornecedor.values())),
    }
