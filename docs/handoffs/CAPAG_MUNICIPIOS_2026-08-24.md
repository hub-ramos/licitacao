> **Estado neste repositório: PENDENTE.** Levantamento recebido em 2026-08-24 e
> arquivado aqui para não se perder. Nada dele foi implementado.
>
> Uma pendência do handoff original já está resolvida: o **projeto de destino**,
> marcado como `[PENDENTE]` nas seções 2, 4 e 8, é **este** repositório
> (`hub-ramos/licitacao`) — Python 3.11, config em YAML sob `config/`, ingestão
> em `src/licita/`, base SQLite em `dados/licitacoes.db`.
>
> O que já foi feito a respeito: a CAPAG entrou em
> `config/fontes_complementares.yml` como a lacuna `risco_de_recebimento`, com as
> URLs abaixo e as perguntas a fazer. Isso NÃO é a implementação — é a inscrição
> da fonte na sonda, que na próxima execução de `python -m licita fontes` devolve
> o código HTTP de cada endpoint. Só depois disso cabe decidir integrar.
>
> Uma nota de método, porque muda o encaixe: este projeto mede **vácuo
> competitivo** — onde há pouca concorrência. A CAPAG mede **risco de o
> município não pagar**. São eixos independentes e é justamente o cruzamento que
> interessa: pouca concorrência com pagador ruim explica a pouca concorrência;
> pouca concorrência com pagador bom é oportunidade limpa. Quando for
> implementada, a CAPAG deve entrar como atributo do município (dimensão), não
> como componente do Índice de Oportunidade.

---

# HANDOFF — CAPAG de Municípios (nota de "bom pagador" para licitações)

**Data:** 2026-08-24
**Escopo:** recorte — pesquisa sobre o indicador público de capacidade de pagamento
de municípios e orientação para implementá-lo em projeto no Claude Code. Nenhum
código foi escrito naquele chat.
**Continuidade:** anexe este arquivo em um chat novo (ou cole no Claude Code)
junto com os arquivos da seção 8.

## 1. Objetivo

Permitir que, antes de participar de uma licitação, seja possível avaliar o risco
de o município não pagar em dia. A pergunta original era qual indicador público /
API fornece uma "nota de bom pagador" do município em escala A, B, C. A resposta é
a CAPAG. O próximo passo é incorporar a consulta da CAPAG (e indicadores
complementares) a um projeto existente.

## 2. Contexto

- **CAPAG** — Capacidade de Pagamento. Classificação de risco fiscal de estados e
  municípios publicada pela Secretaria do Tesouro Nacional (STN). Escala final:
  A, B, C, D, mais A+ e B+ desde a Portaria STN/MF nº 1.583/2023.
- **STN** — Secretaria do Tesouro Nacional.
- **Siconfi** — Sistema de Informações Contábeis e Fiscais do Setor Público
  Brasileiro. Base que alimenta o cálculo da CAPAG.
- **RREO** — Relatório Resumido da Execução Orçamentária (bimestral).
- **RGF** — Relatório de Gestão Fiscal (quadrimestral).
- **DCA** — Declaração de Contas Anuais.
- **MSC** — Matriz de Saldos Contábeis.
- **CKAN** — plataforma de dados abertos usada pelo Tesouro Transparente para
  publicar os datasets (expõe API REST padrão).
- **CAUC** — Serviço Auxiliar de Informações para Transferências Voluntárias;
  registra pendências do ente junto à União.
- **PNCP** — Portal Nacional de Contratações Públicas.
- **Prévia Fiscal** — painel do Tesouro com CAPAG atualizada diariamente conforme
  homologações no Siconfi.
- **Chave de cruzamento entre bases:** código IBGE do município (7 dígitos). A API
  do Siconfi usa `id_ente` = código IBGE.
- **Projeto de destino:** `[PENDENTE]` no handoff original — resolvido, ver a nota
  no topo deste arquivo.

## 3. Decisões tomadas

- Usar a CAPAG da STN como indicador principal de "nota de bom pagador" do
  município. Motivo: é o único indicador público oficial em escala A–D aplicado a
  todos os ~5.570 municípios.
- **Não** tratar a CAPAG como medida de pontualidade de pagamento. Motivo: a CAPAG
  mede risco de crédito para concessão de garantia da União em operações de
  crédito — um município B pode atrasar contrato e um C pode pagar em dia.
  Decisão: complementar com outros indicadores (seção 6).
- Fonte primária de dados para automação: dataset CKAN do Tesouro Transparente
  (`capag-municipios`), **não** a API do Siconfi. Motivo: a API do Siconfi não
  expõe endpoint de CAPAG — só os dados brutos que a alimentam.
- Incorporar isso ao projeto existente via Claude Code. `[PENDENTE]` — forma de
  integração (módulo novo, script isolado, coluna em base existente) não definida.

## 4. O que foi construído

Nada. Nenhum script, planilha ou consulta foi gerado naquele chat. O que existe é
o levantamento das fontes abaixo, validado por busca.

### Metodologia da CAPAG

- Base legal: Portaria MF nº 501/2017, Portaria STN nº 882/2018, Portaria STN/MF
  nº 1.583/2023 (introduziu A+/B+).
- Três subindicadores: **endividamento** (dívida consolidada bruta / receita
  corrente líquida), **poupança corrente** (despesas correntes / receitas
  correntes) e **índice de liquidez** (obrigações financeiras / disponibilidade de
  caixa de recursos não vinculados, antes da inscrição de restos a pagar).
- Cada subindicador recebe A, B ou C. A combinação define a nota final A–D. Duas
  ou mais notas C nos subindicadores → capacidade de pagamento baixa.
- A+/B+: atribuído a quem tem A ou B na CAPAG e nota "Aicf" (≥95%) no Ranking da
  Qualidade da Informação Contábil e Fiscal do Siconfi.
- Apenas entes com A ou B recebem garantia da União em novas operações de crédito.

### Fontes de dados

1. **Painel CAPAG** — página institucional com o painel e a Prévia Fiscal
   (atualizada diariamente):

   ```
   https://www.tesourotransparente.gov.br/temas/estados-e-municipios/capacidade-de-pagamento-capag
   ```

2. **Dataset CKAN** (XLSX com todos os municípios, nota final + nota de cada
   subindicador) — fonte recomendada para automação:

   ```
   https://www.tesourotransparente.gov.br/ckan/dataset/capag-municipios
   ```

   API CKAN padrão para descobrir a URL do XLSX mais recente:

   ```
   https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?id=capag-municipios
   ```

   O JSON retorna `result.resources[]`, cada um com `name`, `format`, `url` e
   `last_modified`. Selecionar o recurso `format == "XLSX"` mais recente.

3. **API do Siconfi** (dados brutos RREO/RGF/DCA/MSC) — pública, sem autenticação,
   resposta JSON `{"items": [...], "hasMore": true/false}`, alguns endpoints
   aceitam `formato=csv`:

   ```
   Base:  https://apidatalake.tesouro.gov.br/ords/siconfi/tt/
   Docs:  https://apidatalake.tesouro.gov.br/docs/siconfi/
   Ex.:   https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo
          https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf
          https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes
   ```

## 5. Estado atual

Fase de levantamento concluída. Fontes identificadas e endpoints confirmados por
busca. Nenhum arquivo salvo, nenhum código escrito, nenhuma integração feita.

## 6. Próximos passos

1. Descrever o projeto de destino ao Claude Code — linguagem, estrutura de pastas,
   onde ficam os módulos de ingestão de dados e onde ficam os caches/dados brutos.
   **Bloqueia todos os passos seguintes.** *(resolvido — ver nota no topo)*
2. **Implementar o cliente CKAN** — função que chama
   `package_show?id=capag-municipios`, localiza o recurso XLSX mais recente por
   `last_modified`, baixa e persiste em cache local com a data de referência no
   nome do arquivo. Não hardcodar a URL do XLSX: ela muda a cada publicação.
3. **Normalizar o XLSX** — padronizar nomes de colunas, garantir código IBGE como
   string de 7 dígitos com zeros à esquerda, expor: código IBGE, UF, município,
   nota CAPAG final, nota de endividamento, nota de poupança corrente, nota de
   liquidez, ano-base/data de referência.
4. **Expor consulta por município** — função que recebe código IBGE (ou UF + nome)
   e devolve o registro CAPAG. Depende do passo 3.
5. **Adicionar indicadores complementares** de risco de pagamento (depende do
   passo 2, independentes entre si):
   - Restos a Pagar Processados e Disponibilidade de Caixa — RGF Anexo 5 / RREO,
     via API do Siconfi. Detecta ente que inscreve dívida sem lastro financeiro.
   - CAUC — pendências do município junto à União. `[PENDENTE]` — fonte/API não
     levantada.
   - Portal da Transparência do município e PNCP — histórico real de liquidação e
     pagamento de empenhos. `[PENDENTE]` — não levantado.
6. **Compor um score de risco de recebimento** combinando CAPAG + restos a pagar +
   disponibilidade de caixa. `[PENDENTE]` — pesos e regra de composição não
   definidos.

## 7. Restrições e regras

- **A CAPAG não é indicador de pontualidade de pagamento.** Documentar isso no
  código/README para evitar leitura errada por quem consumir o dado.
- **Não existe endpoint de CAPAG na API do Siconfi.** Quem procurar por ele perde
  tempo. A CAPAG só sai pelo CKAN (XLSX) ou pelo painel.
- **A URL do XLSX no CKAN muda a cada publicação.** Sempre resolver via
  `package_show`; nunca fixar link direto.
- **O dataset CKAN e a Prévia Fiscal divergem.** O XLSX do CKAN usa os dados do
  Siconfi disponíveis na data de geração do arquivo; a Prévia Fiscal é atualizada
  diariamente. Registrar sempre a data de referência do dado usado.
- **A CAPAG publicada não vincula a posição do Tesouro Nacional.** O cálculo
  definitivo só ocorre na verificação de limites e condições (art. 32 da
  LC 101/2000). É indicativo, não certificação.
- **Ajustes de metodologia entre anos.** O próprio Tesouro sinaliza no dataset que
  houve ajuste nos critérios de cálculo. Não comparar séries históricas de anos
  diferentes sem checar a metodologia vigente em cada uma.
- **Código IBGE é string, não inteiro.** Zeros à esquerda se perdem se tratado como
  número — problema clássico ao ler XLSX com pandas/openpyxl.
- **Ano-base defasado.** A CAPAG divulgada em um ano usa dados do exercício
  anterior (a divulgação de 2024 usou ano-base 2023). Sempre carregar e exibir o
  ano-base junto com a nota.
- Referência legal útil: **Lei 14.133/2021, art. 141** — prazo de até 30 dias para
  pagamento após ateste da nota fiscal em contratos administrativos.

## 8. Arquivos necessários

**Obrigatórios:** nenhum arquivo local. As fontes são todas online e públicas.

**Opcionais / consulta:** estrutura do projeto de destino. *(resolvido — é este
repositório)*

## 9. Prompt de retomada

```
Retomando o trabalho descrito em docs/handoffs/CAPAG_MUNICIPIOS_2026-08-24.md.
Quero incorporar a consulta da CAPAG de municípios a este projeto, para avaliar
risco de recebimento antes de participar de licitações.
Comece pelo passo 2 da seção 6: implementar o cliente CKAN que resolve e baixa o
XLSX mais recente do dataset capag-municipios, respeitando as restrições da
seção 7. Antes disso, leia o veredito da lacuna `risco_de_recebimento` em
dados/fontes_complementares.md — se a sonda ainda não rodou, rode
`python -m licita fontes` no Actions primeiro.
```
