# HANDOFF — Painel de licitações de Jales: coleta destravada e primeiro dado real

**Data:** 2026-08-24
**Escopo:** conversa inteira
**Continuidade:** anexe este arquivo em um chat novo junto com os arquivos da seção 8.

## 1. Objetivo

Base de pesquisa que mede **vácuo competitivo** em licitações da microrregião de
Jales/SP — onde a concorrência é baixa, em quê, e com que frequência se repete.
Nesta sessão a coleta saiu do papel: os bloqueios da Fase 0 foram corrigidos, a
primeira coleta real rodou e o painel HTML foi publicado com dados verdadeiros.
Um plano de cinco etapas foi aprovado e **ainda não foi iniciado**.

## 2. Contexto

**Repositório:** `hub-ramos/licitacao` · público
**Branch de trabalho:** `claude/licitacoes-brasil-mapping-fit8sl` (HEAD = `d35945e`,
empurrado, idêntico ao remoto). A branch padrão é `main`, parada em `9d12583`.
**Stack:** Python 3.11, `requests` + `PyYAML` + `openpyxl`, SQLite, painel HTML estático.
**Execução real:** GitHub Actions (`probe.yml`, `radar.yml`, `historico.yml`).
**Painel publicado:** https://claude.ai/code/artifact/2a65ae0f-ded8-46ce-ade8-3af621bf74a2

**Glossário**
- **PNCP** — Portal Nacional de Contratações Públicas. Duas APIs: consulta
  (`/api/consulta`) e detalhe (`/api/pncp/v1`).
- **Deságio** — `(valorUnitarioEstimado − valorUnitarioHomologado) / valorUnitarioEstimado`.
- **Índice de Oportunidade** — 0 a 100, maior = mais vácuo. Deserção 35%, ausência de
  deságio 30%, concentração HHI 25%, recorrência 10%. Componente sem dado é `None` e
  os pesos são renormalizados sobre os disponíveis.
- **HHI** — Herfindahl-Hirschman normalizado 0..1. 1,0 = um único fornecedor leva tudo.
- **Caso-âncora** — Nova Castilho, Pregão Presencial 007/2026 (leite). Único ponto com
  verdade documentada em PDF. **Não está no PNCP** e **não entra na base** (decisão 1).
- **Modalidades PNCP** — 5 concorrência presencial, 6 pregão eletrônico, 7 pregão
  presencial, 8 dispensa, 9 inexigibilidade, 12 credenciamento.
- **Situação do item** — 1 em andamento, 2 homologado, 3 anulado/revogado/cancelado,
  **4 deserto**, **5 fracassado**.
- **Sonda `fontes`** — `python -m licita fontes`, pergunta à rede quais fontes
  complementares existem. **Nunca foi executada com rede.**
- **AUDESP Fase IV** — cubos LICITACOES/AJUSTES do TCE-SP, todos os municípios
  paulistas desde 2018, por obrigação legal.
- **CAPAG** — Capacidade de Pagamento (Tesouro Nacional), nota A–D de risco fiscal do
  município. Registrada como pendência, não implementada.

**Pessoas:** Anderson (tecnologia e dados, gestora de fundos florestais). Esposa
(operadora), biomédica, alvo profissional declarado é o município de Santa Fé do Sul.

## 3. Decisões tomadas

Distinção obrigatória: **[decidido]** = aprovado pelo usuário; **[sugestão em aberto]**
= proposto por Claude e não confirmado.

1. **[decidido]** Nova Castilho **não** é gravada na base. Fica como teste de regressão
   do cálculo. (Reverte a hipótese inicial de ingerir os PDFs.)
2. **[decidido]** Painel só com dados reais, via Actions. Sem prévia com dado sintético.
   *Revisto depois pelo próprio usuário*: ao pedir "preciso ver o html", aceitou uma
   publicação intermediária com linhas de demonstração explicitamente marcadas.
3. **[decidido]** A busca por fontes complementares cobre 4 lacunas: municípios ausentes
   do PNCP, número de licitantes por sessão, enriquecimento de fornecedor, e compra
   prospectiva (PCA). Depois somou-se a 5ª: risco de recebimento (CAPAG).
4. **[decidido]** Auditoria de "correções mínimas": corrigir só o que bloqueia a coleta,
   registrar o resto como pendência.
5. **[decidido]** Reduzir escopo para calibrar: **um município com dado garantido, um
   mês**. Escolhido Santa Fé do Sul (maior volume medido: 448 contratações na Fase 0),
   período 2026-07-25 a 2026-08-24.
6. **[decidido]** CAPAG entra como **pendência** arquivada e inscrita na sonda `fontes`.
   Quando implementada, deve ser **atributo do município**, não componente do Índice de
   Oportunidade — são eixos independentes (vácuo competitivo × risco de pagamento).
7. **[decidido]** Quantidade mínima do item fica **fora** desta rodada. Não existe no
   schema do PNCP; fonte identificada e registrada como pendência.
8. **[decidido]** Ranking de vencedores nos **quatro** recortes: geral, × segmento,
   × mês/ano, × município.
9. **[decidido por evidência]** `http_massa.pausa_entre_chamadas_s` = 1,0s (era 0,35s).
10. **[decidido por evidência]** Deságio só entra no índice em modalidade **com disputa
    de preço** (1,2,3,4,5,6,7,13). Dispensa e inexigibilidade não têm deságio a medir.
11. **[decidido por evidência]** Deserção só se mede sobre situações **2, 4 e 5**.
    "Em andamento" e "cancelado" ficam de fora.
12. **[revertido]** A latência do PNCP **não** é 2,2s, como registrava o handoff
    anterior. É **0,76s** — os 2,2s eram artefato do próprio rate limiting.

## 4. O que foi construído

Sete commits na branch, de `e77d5ee` a `d35945e`. **62 testes passando** (eram 21).

### 4.1 Freio adaptativo de rate limiting — `src/licita/http.py`

O problema não era retry, era não haver freio: cada 429 era tratado isoladamente e a
varredura seguia no ritmo que causou o bloqueio.

```python
STATUS_EXCESSO = 429

def _frear(self) -> None:
    """Dobra a pausa entre chamadas depois de um 429, até o teto."""
    self.excessos += 1
    self._sucessos_seguidos = 0
    self._pausa_atual = min(max(self._pausa_atual * 2, 0.5), self.pausa_teto)

def _afrouxar(self) -> None:
    """Alivia o freio depois de uma sequência de sucessos, sem voltar abaixo
    da pausa de config, que é o piso."""
    if self._pausa_atual <= self.pausa: return
    self._sucessos_seguidos += 1
    if self._sucessos_seguidos < self.sucessos_para_afrouxar: return
    self._sucessos_seguidos = 0
    self._pausa_atual = max(self.pausa, self._pausa_atual * 0.8)
```

`Retry-After` deixou de ser truncado pelo `backoff_teto` e passou a ter teto próprio
`retry_after_teto_s: 120` (RFC 9110 §10.2.3). Acrescentado `obter_bruto()`, GET que não
exige JSON, para sondar fonte que não é API JSON.

### 4.2 Casamento por palavra inteira — `src/licita/segmentar.py`

**Bug achado:** `cimento` casava dentro de `licenCIAMENTO`; três contratos de software
foram classificados como material de construção. Como `segmento` é o eixo do Índice de
Oportunidade, o erro contaminava tudo em silêncio.

```python
@lru_cache(maxsize=4096)
def _padrao(palavra: str) -> re.Pattern[str]:
    return re.compile(r"(?<![0-9a-z])" + re.escape(palavra) + r"(?:e?s)?(?![0-9a-z])")

def casa(palavra: str, texto_norm: str) -> bool:
    return bool(palavra) and _padrao(palavra).search(texto_norm) is not None
```

### 4.3 Taxonomia de saúde — `config/segmentos.yml`

Removidas as palavras isoladas `capacitacao`, `treinamento`, `educacao permanente`,
`curso de formacao` de `servico_capacitacao_saude`; substituídas por termos que
carregam contexto de saúde. Mesmo tratamento em `servico_indicadores_bi`.
Acrescentados termos de controle vetorial em `servico_vigilancia_saude`
(`termonebulizacao`, `nebulizacao espacial`, `controle vetorial`).

**Medido sobre os 26 objetos reais da Fase 0: de 26 classificados como serviço de
saúde, 6 são.** Superestimado 4,3×. Os 26 viraram corpus de teste em
`tests/test_segmentacao.py` (`NAO_SAO_SAUDE`, 20 itens; `SAO_SAUDE`, 6 itens).

### 4.4 Recusa ≠ bloqueio — `src/licita/probe.py`, `relatorio.py`, `__main__.py`

`Sonda` ganhou o campo `inconclusivo` e o veredito `INCONCLUSIVO`. `descobrir_janela`
dava `break` em qualquer resposta não-ok — um 429 virou "nenhuma janela aceita" no
relatório publicado. Agora 400/422 é recusa real e 429/timeout é inconclusivo.
Sonda nova `medir_ritmo` (séries com pausas 2,0/1,0/0,5/0,25s). **Nunca executada.**

### 4.5 Sonda de fontes complementares — `src/licita/fontes_extra.py` (novo)

`config/fontes_complementares.yml` cataloga **6 candidatas / 16 checagens**, cada uma
com a URL da sua documentação. Quatro vereditos: `RESPONDE`, `RESPONDE VAZIO`,
`NAO SERVE`, `INCONCLUSIVO`. Perfil de retry próprio `http_sonda` (2 tentativas, 20s).
Saída: `dados/fontes_complementares.md` e `dados/fontes.json`.

Candidatas: Querido Diário, AUDESP/TCE-SP, rotas de detalhe do PNCP, `/v1/pca`,
enriquecimento de CNPJ (BrasilAPI/MinhaReceita), CAPAG/Tesouro.

Acessível por `python -m licita fontes` e pela entrada `fontes` do `probe.yml`.
**Executada apenas offline** (14/14 INCONCLUSIVO, comportamento correto).

### 4.6 Recorte de coleta — `src/licita/__main__.py`, `.github/workflows/historico.yml`

```python
def _filtrar(alvos, escolhidos: str | None):
    """Nome desconhecido é erro, não filtro vazio: uma coleta que devolve zero
    porque o nome foi digitado errado é indistinguível de um município que não
    tem licitação."""
```

`--municipio` aceita nome (com ou sem acento) ou código IBGE, separados por vírgula.
`historico.yml` ganhou as entradas `municipio`, `desde`, `ate`, `atas`.
A dimensão `municipio` continua gravada inteira mesmo em coleta restrita.

### 4.7 Correções do Índice de Oportunidade — `src/licita/metricas.py`, `sql/schema.sql`

```python
def desagio_valido(estimado, homologado, quantidade) -> float | None:
    if not estimado or estimado <= 0 or homologado is None:
        return None
    if quantidade and quantidade > 1:
        total = estimado * quantidade
        if abs(homologado - total) < 0.01:      # total publicado no campo unitário
            return 0.0
    bruto = (estimado - homologado) / estimado
    return bruto if bruto >= -1.0 else None
```

Config novo em `config/fontes.yml`:
```yaml
modalidades_com_disputa: [1, 2, 3, 4, 5, 6, 7, 13]
situacoes_item_concluidas: [2, 4, 5]
```

Visões passam a ser recriadas a cada abertura (`DROP VIEW IF EXISTS` antes de
`CREATE VIEW`), porque `CREATE VIEW IF NOT EXISTS` sobre base existente ignora
mudança de fórmula em silêncio.

### 4.8 Painel — `painel/template.html`

Três estados de tema (antes só reagia a `prefers-color-scheme`):
```css
@media (prefers-color-scheme:dark){ :root:not([data-theme=light]){ ... } }
:root[data-theme=dark]{ ... }
```

### 4.9 CAPAG arquivada — `docs/handoffs/CAPAG_MUNICIPIOS_2026-08-24.md`

Handoff íntegro, com cabeçalho marcando PENDENTE e a nota de encaixe conceitual.

## 5. Estado atual

**Tudo commitado e empurrado.** HEAD `d35945e` == `origin/claude/licitacoes-brasil-mapping-fit8sl`.
Working tree limpo. 62 testes passando.

**Dado real na base** (`dados/licitacoes.db`, commitado), coleta de Santa Fé do Sul,
2026-07-25 a 2026-08-24 (run 32724719169, **sucesso, 973s, zero falhas de requisição**):

| tabela | linhas |
|---|---:|
| contratacao | 102 |
| item | 344 |
| resultado | 287 |
| fornecedor | 72 |
| ata | 302 |
| contrato | 121 |
| arquivo | 102 |
| metrica_mun_seg_ano | 16 |
| municipio | 38 |

**Calibração medida:** 1,76s por requisição (554 requisições / 973s), com pausa de
1,0s configurada — logo **latência real do PNCP = 0,76s**. Extrapolação para os 38
municípios: 1 ano = 2,2 h; 2 anos = 3,9 h; **3 anos = 5,7 h, que NÃO cabe** no
`timeout-minutes: 330` do `historico.yml`.

**Modalidades no recorte:** Dispensa 92 (R$ 574.956,53), Pregão Eletrônico 8
(R$ 8.152.822,95), Inexigibilidade 2 (R$ 17.140,00). **Nenhum pregão presencial.**
Dispensa é 90% do volume e 6,5% do dinheiro.

**Ranking do índice após as correções:** carnes 51,4 (único com pregão real, deságio
0,60%), depois copa cozinha / gêneros alimentícios / limpeza higiene / papelaria todos
em 41,7, panificação 41,5, têxtil 40,6, não_classificado 35,8, insumos laboratoriais
21,7, calçados 21,1, madeira construção 21,0, informática 15,2, medicamentos 13,2.
Combustível, laticínios e vigilância em saúde saíram do ranking (sem medida).

**Painel publicado** com esses dados em
https://claude.ai/code/artifact/2a65ae0f-ded8-46ce-ade8-3af621bf74a2 (490 KB).

**Run cancelado:** 32719991084 (Fase 0 ampla, 38 municípios) foi cancelada aos 52 de 90
min. Consequência: **a sonda `fontes` nunca rodou com rede** e as 16 checagens seguem
sem veredito.

**Plano aprovado e NÃO iniciado.** Nenhuma linha da seção 6 foi escrita ainda.

## 6. Próximos passos

Plano aprovado pelo usuário. Ordem de execução:

1. **Paginar `ClientePNCP.itens()`** (`src/licita/pncp.py:190`). Hoje faz `obter()`
   simples e o endpoint pagina: **a distribuição de itens por contratação para seca em
   10** (13 contratações com exatamente 10, nenhuma com mais). Usar `http.paginar()`,
   que já existe. Acrescentar `itens: 50` em `pncp.tamanho_pagina`.
   Atenção: `/itens` devolve **lista crua**, não envelope `{data:[]}` — a parada é por
   página vazia ou página menor que `tamanhoPagina`. **Bloqueia os passos 4 e 5.**
2. **Corrigir o valor do vencedor.** Extrair de `desagio_valido()` uma
   `unitario_confiavel()` e aplicá-la ao homologado, expondo
   `valor_total_homologado_ajustado` na visão. A coluna crua fica intacta.
   Caso real: "JOÃO CARLOS DOS SANTOS, 1 item, R$ 92.686.389,00" = 2.318 × 39.985,50.
3. **Coluna aditiva `link_pncp`** em `contratacao`, montada na coleta com
   `partes_controle_pncp()` (`pncp.py:45`):
   `https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}`.
   `link_sistema_origem` só existe em 8 de 102; `link_pncp` existe em todas.
4. **Linha expansível** no painel, atendendo dois pedidos com um mecanismo: no Radar
   abre os itens da contratação; no Mapa de concorrência abre os itens do
   segmento × município × ano. Índice montado no cliente a partir de `EXPORTS["itens"]`
   — nenhum dado novo precisa ser embarcado.
5. **Aba Vencedores.** Visão `v_vencedor` no grão fornecedor × município × segmento ×
   ano × mês, com seletor "agrupar por" somando no cliente para entregar os quatro
   recortes. Mês derivado de `data_resultado`, com `data_publicacao` como alternativa.
6. **Glossário nos cabeçalhos.** `config/glossario.yml` (novo) mapeando campo →
   explicação em linguagem simples, injetado no painel. Implementar com `title` nativo
   **mais** um "?" clicável — `title` não funciona em toque e o painel é usado no celular.
7. **Recoletar o mesmo recorte** (Santa Fé do Sul, 2026-07-25 a 2026-08-24, ~16 min) e
   conferir dois critérios: o SRP `45138070000149-1-000762/2026` passa de 10 itens para
   o total real, e o ranking não tem mais o valor de R$ 92 milhões. Depois regenerar o
   painel e republicar no **mesmo** endereço de artefato.
8. **Rodar a sonda `fontes` com rede** — `probe.yml` com `rapido=true` e `fontes=true`,
   que é barato e resolve o veredito das 16 checagens. **Independente dos demais.**

## 7. Restrições e regras

### Ambiente da sessão (armadilhas já pagas)

- **O egress bloqueia praticamente todo host externo**, não só `.gov.br`. Verificado
  bloqueado: `pncp.gov.br`, `servicodados.ibge.gov.br`, `transparencia.tce.sp.gov.br`,
  `queridodiario.ok.org.br`, `docs.queridodiario.ok.org.br`, `statuslicitacoes.com.br`,
  `www.transparencia.org.br`, `repositorio.ufsc.br`. Funciona: `api.github.com`.
  **WebSearch funciona** (roda no lado da Anthropic). **WebFetch** funciona só para
  alguns domínios — `gist.github.com` e `github.com` responderam.
- **Toda validação viva roda no GitHub Actions.**
- **`timeout-minutes` cancela o job inteiro** e passos com `if: always()` **não**
  sobrevivem a cancelamento de job. Job que estoura o teto perde tudo.
- **`workflow_dispatch` só enxerga arquivo presente na branch padrão.** Disparar com
  `ref` = branch de trabalho usa a versão daquele ref — por isso sondas novas entram
  como **entrada** do `probe.yml` existente, nunca como workflow novo.
- **O Actions roda com `bash -e`**: `[ -n "$X" ] && VAR=...` **derruba o passo** quando
  X é vazio, porque a linha sai com status 1. Usar `if` explícito.
- **Nunca interpolar `${{ inputs.X }}` dentro do comando** — é injeção de shell por
  quem dispara. Passar por `env:`.
- **O tool Monitor expira em 30 min**, mesmo pedindo mais. Re-armar.
- **Chromium** está em `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`; precisa de
  `--no-sandbox` e de `pip install playwright` (o pacote Python não vem instalado).
  **Não rodar `playwright install`.**
- **O visualizador de artefatos bloqueia download**: `<a download>`, blob e data URI
  são inertes. O botão "Baixar CSV" do painel precisa ser desativado na publicação.

### API do PNCP

- `tamanhoPagina` tem limite **por endpoint**: 50 em `/contratacoes/*`, 500 em `/atas`
  e `/contratos`. O Manual das APIs de Consultas v1.0 diz 500 para todos — **a medição
  vale sobre o manual**, e as duas versões estão registradas em `config/fontes.yml`.
- `codigoModalidadeContratacao` é **obrigatório** em `/contratacoes/publicacao`.
- **Nenhum manual do PNCP documenta rate limit ou 429.** A API devolve 429 com corpo
  HTML em latin-1. Pausa sustentável é medição, não documentação.
- `/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens` **aceita `pagina` e `tamanhoPagina`**
  (Manual de Integração). Devolve **lista crua**, não envelope.
- **O PNCP não devolve CATMAT/CATSER**: 0 de 344 itens preenchidos. O sinal de catálogo
  é descrito em `segmentar.py` como o mais confiável e **nunca dispara**. Explica parte
  dos 57% de `nao_classificado`.
- **Não existe quantidade mínima** no schema do item. DTO documentado: `numeroItem`,
  `materialOuServico`, `tipoBeneficioId`, `incentivoProdutivoBasico`, `descricao`,
  `quantidade`, `unidadeMedida`, `valorUnitarioEstimado`, `valorTotal`,
  `criterioJulgamentoId`. Limite de 1000 itens no envio.
- URL pública canônica: `https://pncp.gov.br/app/editais/{cnpj}/{ano}/{sequencial}`.

### Qualidade do dado publicado pelos órgãos

- **Órgão publica o valor TOTAL no campo do unitário.** Assinatura:
  `homologado ≈ quantidade × estimado`. Caso real: "Uva Núbia", 2.318 kg, R$ 17,25/kg,
  "unitário" homologado de R$ 39.985,50. Sem tratamento vira deságio de −231.700%.
- **Deságio é zero por construção em dispensa e inexigibilidade** — ali o "estimado"
  publicado é o próprio contratado. 271 de 275 itens de dispensa deram zero exato.
- **`linkSistemaOrigem` é raro**: 8 de 102 contratações.

### Regras de método

- **Ausência de medida não é medida de ausência.** Vale para 429 × cobertura vazia,
  para item em andamento × item deserto, e para sonda bloqueada × fonte inexistente.
- **Sonda que não usa os mesmos parâmetros da coleta não valida a coleta.**
- **Coluna nova é aditiva; coluna existente nunca é removida nem renomeada.**
- Nome de município desconhecido no filtro é **erro**, não filtro vazio.
- Cuidado com especificidade de CSS: `.leia p` (0,1,1) vence `.ancora` (0,1,0).

### Regras de negócio (do handoff anterior, ainda válidas)

- Nunca dar lance sem proposta firme de preço do fornecedor, por escrito.
- Nunca assessorar duas empresas concorrentes no mesmo item/pregão (art. 337-F CP).
- ARP é estimativa, não garantia. Execução real fica entre 60% e 90%.
- Simples Nacional incide sobre faturamento bruto, não sobre margem.
- Medicamentos exigem AFE/ANVISA e responsável técnico farmacêutico — `bloqueado`.
- Lei 14.133/2021, art. 141: até 30 dias para pagamento após ateste da nota fiscal.

### Privacidade

`.gitignore` bloqueia `*.pdf`, `*curriculo*`, `*CV_*`. Currículo nunca é commitado.

## 8. Arquivos necessários

**Obrigatórios**
- Este arquivo.
- O repositório `hub-ramos/licitacao`, branch `claude/licitacoes-brasil-mapping-fit8sl`,
  commit `d35945e`. Todo o código, configuração e a base com dado real estão lá.

**Opcionais / consulta (todos já dentro do repositório)**
- `dados/licitacoes.db` — base com a coleta real de Santa Fé do Sul.
- `dados/painel.html` — painel gerado com dado real.
- `dados/relatorio_cobertura.md` e `dados/probe.json` — Fase 0 de 2026-08-24, com as
  846 contratações agregadas e as 106 falhas. **Anteriores às correções.**
- `docs/handoffs/CAPAG_MUNICIPIOS_2026-08-24.md` — pendência da CAPAG.
- `config/fontes_complementares.yml` — as 6 candidatas e 16 checagens sem veredito.
- `HANDOFF_BASE_LICITACOES_JALES_20260824.md` — handoff anterior. **Atenção:** contém
  dois números hoje sabidamente errados — latência de 2,2s (é 0,76s) e "19 de 26 falsos
  positivos" na taxonomia (são 20 de 26).

## 9. Prompt de retomada

```
Retomando o painel de licitações de Jales. Contexto no HANDOFF anexo — leia antes de
responder. Repositório hub-ramos/licitacao, branch claude/licitacoes-brasil-mapping-fit8sl,
HEAD d35945e, 62 testes passando, base com dado real de Santa Fé do Sul já commitada.

O plano da seção 6 foi aprovado e não foi iniciado. Comece pelo passo 1: paginar
ClientePNCP.itens() em src/licita/pncp.py, que hoje trunca toda contratação em 10 itens
e é a causa do detalhamento incompleto no painel. Depois siga os passos 2 e 3, que são
pré-requisitos da recoleta do passo 7.

Lembre que esta sessão não alcança nenhum host externo: valide no GitHub Actions.
```
