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

### Automação

Três workflows do GitHub Actions:

| Workflow | Quando | O que faz |
|---|---|---|
| `probe.yml` | Manual | Fase 0: valida endpoints, testa o caso-âncora, mede cobertura |
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
| `fontes.yml` | Endpoints, modalidades, janelas, rate limit |

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

## O que esta base ainda não faz

| Pendência | Por quê | Caminho |
|---|---|---|
| Contagem real de licitantes | Não existe na API; só no PDF da ata | Parser best-effort sobre `arquivo.url`. Os proxies já respondem a pergunta de negócio |
| AUDESP Fase IV (TCE-SP) | Cubos são arquivos para download, não REST | Licitações de todos os municípios paulistas desde 2018, por obrigação legal, **independente de publicação no PNCP**. Pode resolver a cobertura do presencial — e talvez traga contagem de participantes |
| Sanções CEIS/CNEP | Não implementado | Portal da Transparência federal, chave gratuita. Due diligence de concorrente e fornecedor |
| Lado da demanda em saúde | Não implementado | CNES, SIOPS e população para detectar município que compra abaixo do porte |
| Antecipação epidemiológica | Não implementado | SINAN/InfoDengue: curva de arbovirose sobe antes de o edital sair |

## Aviso

Dados pessoais não entram neste repositório. O `.gitignore` bloqueia PDFs e
arquivos de currículo.
