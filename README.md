# Base de pesquisa de licitações — microrregião de Jales/SP

Instrumento de medição de **vácuo competitivo** em licitações públicas dos
municípios da região de Jales, Santa Fé do Sul, Fernandópolis e General Salgado.

Não é um agregador de editais — desses já existem vários. A pergunta que esta
base responde é outra: **onde a concorrência é baixa, em quê, e com que
frequência isso se repete?**

## De onde vem a pergunta

O caso que originou o projeto: Nova Castilho, Pregão Presencial 007/2026,
registro de preços para 21.000 litros de leite.

| Fase | Valor |
|---|---|
| Estimativa da prefeitura | R$ 7,01/L |
| Proposta única | R$ 6,95/L |
| Negociação do pregoeiro | **R$ 6,92/L** |

Deságio final: **1,28%**. Compareceu **um único licitante**, apesar de
publicação em diário oficial, jornal local, site e portal da transparência.

Sessões com um licitante e deságio de ~1% são o padrão da região, não a exceção.
O gargalo competitivo desses municípios não é preço, capital ou habilitação — é
**presença física na sessão**, já que municípios com até 20.000 habitantes ainda
podem usar pregão presencial (art. 176, II da Lei 14.133/2021).

## Como a concorrência é medida

O PNCP **não publica quantos licitantes compareceram** a uma sessão. Esse número
só existe no PDF da ata. A base substitui a contagem por quatro sinais que a API
entrega e que medem a mesma coisa:

| Sinal | O que indica | Peso |
|---|---|---|
| **Deserção** — item deserto ou fracassado | Concorrência zero, comprovada. E a melhor oportunidade que existe: a prefeitura terá que comprar de novo | 35% |
| **Ausência de deságio** | Disputa real derruba preço; disputa inexistente não derruba. Abaixo de ~3% é assinatura de licitante único | 30% |
| **Concentração (HHI)** | Um CNPJ levando tudo = mercado capturado | 25% |
| **Recorrência** | Item que se repete todo ano é previsível, e previsível dá para preparar | 10% |

Compõem o **Índice de Oportunidade**, de 0 a 100. Componente sem dado não é
chutado: os pesos são renormalizados sobre o que existe.

## Instalação

```bash
pip install -r requirements.txt
export PYTHONPATH=src          # no Windows: set PYTHONPATH=src
```

## Uso

```bash
python -m licita probe        # Fase 0 — valide as fontes ANTES de qualquer coisa
python -m licita fontes       # sonda as fontes complementares ao PNCP
python -m licita municipios   # resolve os municípios-alvo pelo IBGE
python -m licita historico    # backfill: contratações, itens, resultados
python -m licita radar        # varredura rápida de propostas em aberto
python -m licita atas         # atas de registro de preço e contratos
python -m licita metricas     # recalcula o Índice de Oportunidade
python -m licita exportar     # CSV, XLSX e painel HTML
python -m licita tudo         # histórico + atas + métricas + exports
```

Saídas em `dados/`:

- `licitacoes.db` — base SQLite completa
- `painel.html` — painel com filtros, abre em qualquer navegador, sem instalar nada
- `*.csv` — separador `;` e BOM, abrem direto no Excel pt-BR
- `licitacoes.xlsx` — mesmas tabelas em abas, com filtro automático
- `relatorio_cobertura.md` — saída da Fase 0
- `fontes_complementares.md` — veredito, por execução, sobre cada fonte candidata

### Automação

Três workflows do GitHub Actions:

| Workflow | Quando | O que faz |
|---|---|---|
| `probe.yml` | Manual | Fase 0: valida endpoints, testa o caso-âncora, mede cobertura. Entrada `fontes` sonda também as fontes complementares |
| `radar.yml` | Dias úteis, 06:00 BRT | Propostas em aberto + exports |
| `historico.yml` | Domingo, 04:00 BRT | Backfill completo + atas + métricas + exports |

Todos commitam a base e os exports no próprio repositório.

## Comece pela Fase 0

**Rode `probe` antes de confiar em qualquer número desta base.**

Este código foi escrito num ambiente sem acesso de rede às APIs públicas
brasileiras — a política de egress bloqueia todo host `.gov.br` (403 no CONNECT,
verificado em `pncp.gov.br`, `dadosabertos.compras.gov.br`, `servicodados.ibge.gov.br`,
`apidadosabertos.saude.gov.br`, `apidatalake.tesouro.gov.br`,
`transparencia.tce.sp.gov.br` e `api.portaldatransparencia.gov.br`).

As rotas foram implementadas a partir da documentação oficial e de
implementações de terceiros, com acesso a campo tolerante a ausência e
degradação graciosa. Mas **nada foi exercitado contra a API real**. O `probe`
roda no GitHub Actions, que alcança as APIs, e produz
`dados/relatorio_cobertura.md` respondendo:

1. Os endpoints existem e devolvem o que a documentação promete?
2. **O PNCP contém o Pregão 007/2026 de Nova Castilho?** É o teste que decide o
   projeto — se o presencial de município pequeno não está lá, a base não serve
   para o padrão da região, e o cubo AUDESP do TCE-SP passa de complemento a
   peça obrigatória.
3. Qual a cobertura real por município, ano e modalidade?
4. Que tamanho tem o mercado de serviço técnico em saúde na região?

As rotas menos confirmadas são as de detalhe (`/api/pncp/v1/.../itens`,
`.../resultados`, `.../arquivos`) — justamente as que trazem vencedor e valor
homologado por item. Se falharem, o coletor degrada para o nível de contratação
e a análise perde o deságio por item.

## Configuração

Tudo em `config/`, sem tocar em código:

| Arquivo | Conteúdo |
|---|---|
| `municipios.yml` | Regiões-alvo, extras, prioritários e o caso-âncora |
| `segmentos.yml` | Taxonomia: palavras-chave, grupos CATMAT/CATSER, produto × serviço |
| `fontes.yml` | Endpoints, modalidades, janelas, perfis de retry e ritmo |
| `fontes_complementares.yml` | Candidatas a fonte complementar, cada uma com a URL da sua documentação |

Os **códigos IBGE não são fixados à mão** de propósito: são resolvidos pelo nome
da região imediata na API de Localidades. Código digitado errado produz base
silenciosamente incompleta — o município some e nada acusa. O resultado fica em
`dados/municipios.json`, versionado, para a coleta sobreviver ao IBGE fora do ar.

### Duas particularidades que valem saber

**Compra de saúde sai no CNPJ do Fundo Municipal de Saúde**, que é distinto do
CNPJ da prefeitura. Por isso o filtro é por `codigoMunicipioIbge`, que captura os
dois. Filtrar por CNPJ do órgão perderia quase toda a compra de saúde.

**Serviço técnico especializado** (consultoria em vigilância, telessaúde,
capacitação, indicadores) é comprado por dispensa, inexigibilidade e
credenciamento — não por pregão. Por isso as modalidades 8, 9 e 12 entram na
coleta com o mesmo peso do pregão, e o catálogo `CATSER` se soma ao `CATMAT`.

## Testes

```bash
python -m unittest discover -s tests -v
```

O teste central é a **regressão do caso-âncora**: a base tem que reproduzir os
números dos PDFs oficiais de Nova Castilho — 21.000 L, R$ 145.320,00 de ARP,
deságio de 1,28%, fornecedor único, HHI 1,0. É o único ponto do projeto com
verdade verificada de forma independente. Se ele quebrar, algo na cadeia de
coleta ou de cálculo saiu do lugar.

Também é testada a **idempotência**: rodar a coleta duas vezes não pode duplicar
linha nem alterar métrica.

## Estabilidade dos exports

Coluna nova é sempre acrescentada; coluna existente **nunca** é removida nem
renomeada. Os CSV alimentam relatórios de BI externos, e coluna que desaparece
quebra relatório sem avisar.

## Fontes complementares: perguntar, não supor

A Fase 0 de 2026-08-24 mediu que o PNCP **não** cobre a região inteira: 17 dos
38 municípios voltaram sem nenhuma contratação, e o caso-âncora de Nova Castilho
não está lá. `config/fontes_complementares.yml` cataloga as candidatas a tapar
esse buraco, cada uma com a URL da sua documentação e as perguntas a fazer.

`python -m licita fontes` executa as perguntas e escreve
`dados/fontes_complementares.md` com o código HTTP de cada requisição. A regra é
a mesma do `probe`: **candidato sem execução não vira conclusão**, e quatro
vereditos são possíveis —

| Veredito | Significa | O que fazer |
|---|---|---|
| `RESPONDE` | Existe, responde e trouxe registro | Só aqui cabe decidir integrar |
| `RESPONDE VAZIO` | Existe e respondeu, mas não tem o que se procurou | Resposta negativa legítima |
| `NAO SERVE` | Avaliou a requisição e recusou (4xx que não seja 429) | Parâmetro errado ou rota inexistente |
| `INCONCLUSIVO` | Bloqueio, timeout ou 5xx | Repetir antes de concluir qualquer coisa |

A distinção entre as duas últimas não é preciosismo: na execução de 24/08, 103
respostas HTTP 429 do PNCP foram lidas como ausência de dados, e quase se
concluiu que o PNCP não cobria a região.

## Divergências entre documentação e API viva

Ficam registradas onde afetam a coleta, com as duas versões, para que ninguém
"corrija" a medição de volta lendo só o manual:

| Ponto | Documentação | Medição |
|---|---|---|
| `tamanhoPagina` | Manual das APIs de Consultas v1.0: até 500 em todos os endpoints | HTTP 400 acima de 50 em `/contratacoes/*`; 500 aceito em `/atas` e `/contratos` |
| Rate limit | Nenhum manual do PNCP cita limite ou HTTP 429 | A API devolve 429 com corpo HTML em latin-1; 0,35s de pausa produziu 103 bloqueios em 29 municípios |

## Pendências conhecidas, ainda não corrigidas

| Pendência | Onde | Por que importa |
|---|---|---|
| Campos do PNCP descartados | `sql/schema.sql`, `src/licita/coleta.py` | A API devolve `justificativaPresencial`, `tipoInstrumentoConvocatorioNome`, `linkProcessoEletronico`, `fontesOrcamentarias` e `orgaoSubRogado`. O primeiro fala direto com a tese de que o gargalo é a sessão presencial |
| `contrato` sem vínculo com a contratação | `src/licita/coleta.py` | `numeroControlePncpCompra` vem no retorno e não é gravado. É o caminho alternativo para saber quem ganhou quando as rotas de detalhe falham |
| Outlier de Três Fronteiras | `dados/relatorio_cobertura.md` | 1 contratação, R$ 371.276.147,04, município de ~6 mil habitantes. Erro de digitação na fonte ou contrato atípico — não investigado |
| Atas e contratos varridos por CNPJ | `src/licita/coleta.py` | Uma requisição por órgão por janela, onde uma por janela com filtro local resolveria |
| Backfill de 3 anos não cabe no workflow | `.github/workflows/historico.yml` | Com a latência de 2,2s medida no runner e a pausa de 1,0s, 3 anos custam ~10,4 h contra timeout de 5,5 h. A primeira coleta real vai com `anos=1` (~4 h); o histórico completo precisa ser fatiado |

## O que esta base ainda não faz

| Pendência | Por quê | Caminho |
|---|---|---|
| Contagem real de licitantes | Não existe na API; só no PDF da ata | Parser best-effort sobre `arquivo.url`. Os proxies já respondem a pergunta de negócio |
| AUDESP Fase IV (TCE-SP) | Cubos são arquivos para download, não REST | Licitações de todos os municípios paulistas desde 2018, por obrigação legal, **independente de publicação no PNCP**. Pode resolver a cobertura do presencial — e talvez traga contagem de participantes |
| **CAPAG do município** | Levantado, não implementado | Nota A–D de capacidade de pagamento, do Tesouro Nacional. Responde a outra pergunta que não a desta base: **se o município paga**. Levantamento em [`docs/handoffs/CAPAG_MUNICIPIOS_2026-08-24.md`](docs/handoffs/CAPAG_MUNICIPIOS_2026-08-24.md); inscrita na sonda como lacuna `risco_de_recebimento` |
| Sanções CEIS/CNEP | Não implementado | Portal da Transparência federal, chave gratuita. Due diligence de concorrente e fornecedor |
| Lado da demanda em saúde | Não implementado | CNES, SIOPS e população para detectar município que compra abaixo do porte |
| Antecipação epidemiológica | Não implementado | SINAN/InfoDengue: curva de arbovirose sobe antes de o edital sair |

## Aviso

Dados pessoais não entram neste repositório. O `.gitignore` bloqueia PDFs e
arquivos de currículo.
