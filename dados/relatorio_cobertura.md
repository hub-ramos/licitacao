# Relatório de cobertura — Fase 0

Gerado em 2026-08-24 01:22 UTC · 38 municípios-alvo

Este relatório é a primeira coisa a ler no projeto. Ele valida se as fontes existem e se contêm o que a análise precisa. Nada nas fases seguintes deve ser considerado confiável antes de as seções 1 e 2 saírem limpas.

---

## 1. Endpoints

| Endpoint | Veredito | HTTP | Registros | Observação |
|---|---|---|---|---|
| IBGE · municípios da UF | **OK** | 200 | 645 | Resolve os códigos IBGE dos municípios-alvo. |
| PNCP · contratações por publicação | **OK** | 200 | 10 | Fundação do histórico. Modalidade 7 = pregão presencial. |
| PNCP · contratações com proposta aberta | **OK** | 200 | 10 | Base do radar diário de oportunidades. |
| PNCP · atas de registro de preço | **OK** | 200 | 10 |  |
| PNCP · contratos | **OK** | 200 | 10 | Traz niFornecedor e valorGlobal: é a fonte de quem ganha o quê. |
| PNCP · rotas de detalhe (itens/resultados/arquivos) | **FALHA** | — | — | não testadas: o caso-âncora não foi localizado na API de consulta |
| PNCP · filtro por município (testado em Jales) | **OK** | 200 | 1 | Variante que funciona: **codigoMunicipioIbge só**. codigoMunicipioIbge só: HTTP 200 · 10 registros | codigoMunicipioIbge + uf: HTTP 200 · 10 registros | codigoMunicipioIbge como int: HTTP 200 · 10 registros | codigoUnidadeAdministrativa: HTTP 422 · — registros | uf só (controle): HTTP 200 · 10 registros |
| PNCP · maior tamanhoPagina aceito | **OK** | 200 | 50 | Maior aceito: **50**. `tamanho_pagina` está em {'contratacoes_publicacao': 50, 'contratacoes_proposta': 50, 'atas': 500, 'contratos': 500, 'padrao': 50}. 10: HTTP None·— | 50: HTTP 200·50 | 100: HTTP 400·— | 500: HTTP 400·— |
| PNCP · maior janela de datas aceita | **FALHA** | — | 0 | Nenhuma janela testada foi aceita — verificar os parâmetros. |

<details><summary>Campos observados em cada retorno</summary>

**IBGE · municípios da UF**

`id`, `microrregiao`, `nome`, `regiao-imediata`

**PNCP · contratações por publicação**

`amparoLegal`, `anoCompra`, `dataAberturaProposta`, `dataAtualizacao`, `dataAtualizacaoGlobal`, `dataEncerramentoProposta`, `dataInclusao`, `dataPublicacaoPncp`, `emendaParlamentar`, `fontesOrcamentarias`, `informacaoComplementar`, `justificativaPresencial`, `linkProcessoEletronico`, `linkSistemaOrigem`, `modalidadeId`, `modalidadeNome`, `modoDisputaId`, `modoDisputaNome`, `numeroCompra`, `numeroControlePNCP`, `objetoCompra`, `orgaoEntidade`, `orgaoSubRogado`, `processo`, `sequencialCompra`, `situacaoCompraId`, `situacaoCompraNome`, `srp`, `tipoInstrumentoConvocatorioCodigo`, `tipoInstrumentoConvocatorioNome`, `unidadeOrgao`, `unidadeSubRogada`, `usuarioNome`, `valorTotalEstimado`, `valorTotalHomologado`

**PNCP · contratações com proposta aberta**

`amparoLegal`, `anoCompra`, `dataAberturaProposta`, `dataAtualizacao`, `dataAtualizacaoGlobal`, `dataEncerramentoProposta`, `dataInclusao`, `dataPublicacaoPncp`, `emendaParlamentar`, `fontesOrcamentarias`, `informacaoComplementar`, `justificativaPresencial`, `linkProcessoEletronico`, `linkSistemaOrigem`, `modalidadeId`, `modalidadeNome`, `modoDisputaId`, `modoDisputaNome`, `numeroCompra`, `numeroControlePNCP`, `objetoCompra`, `orgaoEntidade`, `orgaoSubRogado`, `processo`, `sequencialCompra`, `situacaoCompraId`, `situacaoCompraNome`, `srp`, `tipoInstrumentoConvocatorioCodigo`, `tipoInstrumentoConvocatorioNome`, `unidadeOrgao`, `unidadeSubRogada`, `usuarioNome`, `valorTotalEstimado`, `valorTotalHomologado`

**PNCP · atas de registro de preço**

`anoAta`, `cancelado`, `cnpjOrgao`, `cnpjOrgaoSubrogado`, `codigoUnidadeOrgao`, `codigoUnidadeOrgaoSubrogado`, `dataAssinatura`, `dataAtualizacao`, `dataAtualizacaoGlobal`, `dataCancelamento`, `dataInclusao`, `dataPublicacaoPncp`, `nomeOrgao`, `nomeOrgaoSubrogado`, `nomeUnidadeOrgao`, `nomeUnidadeOrgaoSubrogado`, `numeroAtaRegistroPreco`, `numeroControlePNCPAta`, `numeroControlePNCPCompra`, `objetoContratacao`, `possibilidadeAdesao`, `usuario`, `vigenciaFim`, `vigenciaInicio`

**PNCP · contratos**

`anoContrato`, `categoriaProcesso`, `codigoPaisFornecedor`, `dataAssinatura`, `dataAtualizacao`, `dataAtualizacaoGlobal`, `dataPublicacaoPncp`, `dataVigenciaFim`, `dataVigenciaInicio`, `emendaParlamentar`, `frutoAdesao`, `identificadorCipi`, `informacaoComplementar`, `niFornecedor`, `niFornecedorSubContratado`, `nomeFornecedorSubContratado`, `nomeRazaoSocialFornecedor`, `numeroContratoEmpenho`, `numeroControlePNCP`, `numeroControlePncpAta`, `numeroControlePncpCompra`, `numeroParcelas`, `numeroRetificacao`, `objetoContrato`, `orgaoEntidade`, `orgaoSubRogado`, `processo`, `receita`, `sequencialContrato`, `temRemanejamento`, `tipoContrato`, `tipoPessoa`, `tipoPessoaSubContratada`, `unidadeOrgao`, `unidadeSubRogada`, `urlCipi`, `usuarioNome`, `valorAcumulado`, `valorGlobal`, `valorInicial`

</details>

> **Atenção:** 2 de 9 endpoints não responderam como esperado. Os módulos que dependem deles degradam em vez de quebrar, mas a base ficará incompleta até que sejam corrigidos.

---

## 2. Teste de aceitação — Nova Castilho, Pregão Presencial 007/2026

É o único ponto do projeto com verdade conhecida de forma independente, extraída dos PDFs oficiais e registrada no handoff. Se o PNCP não contiver este pregão, a base não serve para pregão presencial de município pequeno — que é o padrão da região — e o cubo AUDESP do TCE-SP passa de complemento a peça obrigatória.

**Resultado: NÃO ENCONTRADO.**

Duas leituras possíveis, e a diferença entre elas decide o projeto:

1. O município não publicou este pregão no PNCP. Se for o caso, a cobertura de presencial é estruturalmente incompleta e o AUDESP Fase IV vira obrigatório.
2. Publicou, mas sob número, modalidade ou órgão diferentes do esperado. Confira a tabela de cobertura da seção 3 antes de concluir: se o município aparece com contratações no período, é este o caso.

---

## 3. Cobertura por município

> **106 requisições de coleta falharam.** Cobertura vazia abaixo pode ser efeito disto, não ausência de licitações.

| HTTP | Ocorrências |
|---|---:|
| 429 | 103 |
| sem resposta | 3 |

Exemplos:

- `contratacoes 3524808 mod=8 2026-01-01..2026-08-24` → None: ReadTimeout: HTTPSConnectionPool(host='pncp.gov.br', port=443): Read timed out. (read timeout=15)
- `contratacoes 3546603 mod=8 2026-01-01..2026-08-24` → 429: HTTP 429: <html>
<head>
    <meta charset="UTF-8">
    <title>Limite de RequisiÃ§Ãµes Excedido</title>
</head>
<body>
    <h2>Limite de requisiÃ§Ãµes excedido</
- `contratacoes 3546603 mod=9 2026-01-01..2026-08-24` → 429: HTTP 429: <html>
<head>
    <meta charset="UTF-8">
    <title>Limite de RequisiÃ§Ãµes Excedido</title>
</head>
<body>
    <h2>Limite de requisiÃ§Ãµes excedido</
- `contratacoes 3546603 mod=12 2026-01-01..2026-08-24` → 429: HTTP 429: <html>
<head>
    <meta charset="UTF-8">
    <title>Limite de RequisiÃ§Ãµes Excedido</title>
</head>
<body>
    <h2>Limite de requisiÃ§Ãµes excedido</
- `contratacoes 3502606 mod=5 2026-01-01..2026-08-24` → 429: HTTP 429: <html>
<head>
    <meta charset="UTF-8">
    <title>Limite de RequisiÃ§Ãµes Excedido</title>
</head>
<body>
    <h2>Limite de requisiÃ§Ãµes excedido</

Contratações que o PNCP efetivamente tem, por município. Município com zero contratações é sinal de vácuo de **fonte**, não de mercado — não confundir os dois.

| Município | Contratações | Anos | Presencial (5,7) | Serviço técnico (8,9,12) | Valor estimado |
|---|---:|---:|---:|---:|---:|
| Santa Fé do Sul | 448 | 1 | 3 | 400 | R$ 58.337.606,12 |
| Jales | 82 | 1 | 2 | 21 | R$ 71.037.973,25 |
| Santa Salete | 50 | 1 | 0 | 29 | R$ 15.296.264,44 |
| São Francisco | 42 | 1 | 12 | 15 | R$ 9.474.481,22 |
| Rubinéia | 41 | 1 | 8 | 22 | R$ 17.987.785,93 |
| Mira Estrela | 35 | 1 | 2 | 33 | R$ 5.083.418,13 |
| São João das Duas Pontes | 27 | 1 | 2 | 5 | R$ 13.698.400,15 |
| Urânia | 27 | 1 | 0 | 8 | R$ 16.652.426,98 |
| Aspásia | 17 | 1 | 0 | 2 | R$ 4.474.144,73 |
| Meridiano | 14 | 1 | 4 | 10 | R$ 2.575.029,61 |
| Turmalina | 13 | 1 | 0 | 0 | R$ 12.365.405,23 |
| Nova Canaã Paulista | 12 | 1 | 0 | 0 | R$ 2.183.281,44 |
| Guarani d'Oeste | 10 | 1 | 0 | 7 | R$ 937.236,82 |
| Santana da Ponte Pensa | 8 | 1 | 0 | 8 | R$ 65.352,86 |
| Aparecida d'Oeste | 5 | 1 | 0 | 5 | R$ 193.166,65 |
| Populina | 5 | 1 | 2 | 2 | R$ 4.748.296,77 |
| Pedranópolis | 4 | 1 | 2 | 0 | R$ 1.183.147,12 |
| Mesópolis | 2 | 1 | 0 | 2 | R$ 60.847,22 |
| Paranapuã | 2 | 1 | 0 | 0 | R$ 2.502.687,00 |
| General Salgado | 1 | 1 | 0 | 1 | — |
| Três Fronteiras | 1 | 1 | 0 | 0 | R$ 371.276.147,04 |

**Sem nenhuma contratação no PNCP (17):** Dirce Reis, Dolcinópolis, Estrela d'Oeste, Fernandópolis, Indiaporã, Macedônia, Marinópolis, Nova Castilho, Ouroeste, Palmeira d'Oeste, Pontalinda, Santa Albertina, Santa Clara d'Oeste, Santa Rita d'Oeste, Suzanápolis, São João de Iracema, Vitória Brasil.

Estes são os candidatos naturais à camada AUDESP.

### Distribuição por modalidade

| Modalidade | Contratações |
|---|---:|
| 8 — Dispensa de Licitação | 513 |
| 6 — Pregão - Eletrônico | 239 |
| 9 — Inexigibilidade | 55 |
| 7 — Pregão - Presencial | 31 |
| 5 — Concorrência - Presencial | 6 |
| 12 — Credenciamento | 2 |

---

## 4. Mercado de serviço técnico em saúde

Contratações em dispensa, inexigibilidade e credenciamento cujo objeto classifica como serviço do domínio saúde. Dimensiona a segunda linha de negócio antes de qualquer investimento nela.

**26 contratações** em 8 municípios, somando R$ 1.859.173,26 em valor estimado.

| Segmento | Contratações |
|---|---:|
| servico_capacitacao_saude | 19 |
| servico_saude_digital | 2 |
| servico_vigilancia_saude | 2 |
| servico_laboratorial | 1 |
| servico_saude_assistencial | 1 |
| servico_indicadores_bi | 1 |

### Amostra de objetos

- **Jales** (servico_capacitacao_saude): Contratação de empresa especializada no fornecimento de licença de uso de  sistema/software para orçamentação eletrônica de peças de motocicletas, veículos automotivos, maquinas pesadas e implementos 
- **Jales** (servico_capacitacao_saude): Contratação de empresa especializada na prestação de serviços de capacitação e treinamento de profissionais no curso In-Company de Gestão Patrimonial - Reconhecimento, Controle e Desfazimento de Bens,
- **Jales** (servico_capacitacao_saude): O Registro de Preço para eventual aquisição de (munição operacional de treinamento para uso institucional atendendo às necessidades da Guarda Civil Municipal), objeto deste Estudo Técnico Preliminar, 
- **Jales** (servico_capacitacao_saude): Contratação de empresa especializada para prestação de serviços de capacitação e treinamento de profissionais no SEMINÁRIO EMPRETEC, por tempo determinado.
- **Jales** (servico_capacitacao_saude): Contratação de empresa especializada para prestação de serviços de capacitação e treinamento de profissionais no 11° Congresso Internacional de Educação do Noroeste Paulista, com entrega integral, por
- **Jales** (servico_capacitacao_saude): Contratação de empresa para prestação de serviços de capacitação e treinamento de profissionais no evento Expoeducare 2026- com o tema Escola e Familia: uma parceria que precisa dar certo, que acontec
- **Jales** (servico_capacitacao_saude): Contratação de empresa para prestação de serviços de capacitação e treinamento de profissionais na Capacitação em Processos Administrativos (IEG-M), por tempo determinado.
- **Jales** (servico_capacitacao_saude): Contratação de empresa para prestação de serviços de capacitação e treinamento de profissionais no curso de Acompanhamento Familiar em Grupo no SUAS e Coordenação de CRAS e CREAS, por tempo determinad
- **Santa Fé do Sul** (servico_saude_digital): Contratação de hospedagem VPS para hospedagem do sistema e-SUS
- **Santa Fé do Sul** (servico_capacitacao_saude): Prestação de serviços, visando ministrar assessoria e capacitação presencial para servidor lotado junto ao Setor de Contabilidade do SantaFePrev para fechamento de balanço contábil do exercício de 202
- **Santa Fé do Sul** (servico_capacitacao_saude): Contratação de empresa especializada para prestação de serviços de treinamento e capacitação em Língua Brasileira de Sinais (Libras), a ser realizado na Casa da Juventude, conforme condições, especifi
- **Santa Fé do Sul** (servico_saude_digital): Contratação de serviço para UPGRADE de disco 50GB para o Sistema eSUS
- **Guarani d'Oeste** (servico_vigilancia_saude): CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA PRESTAÇÃO DE SERVIÇOS DE TERMONEBULIZAÇÃO EM VIAS PÚBLICAS, COM UTILIZAÇÃO DE EQUIPAMENTOS HOMOLOGADOS E PRODUTOS INSETICIDAS DEVIDAMENTE REGISTRADOS PELA ANV
- **Meridiano** (servico_capacitacao_saude): CONTRATAÇÃO DE SERVIÇOS TÉCNICOS ESPECIALIZADOS DE NATUREZA PREDOMINANTEMENTE INTELECTUAL PARA A REALIZAÇÃO DE CAPACITAÇÃO E TREINAMENTO PRESENCIAL SOBRE A ELABORAÇÃO E EXECUÇÃO DA LEI ORÇAMENTÁRIA AN
- **Mira Estrela** (servico_capacitacao_saude): “CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA MINISTRAR CURSO DE FORMAÇÃO E CAPACITAÇÃO DE PROFISSIONAIS PARA ATUAÇÃO NO CONTEXTO DA EDUCAÇÃO ESPECIAL INCLUSIVA, CONTEMPLANDO CONHECIMENTOS TEÓRICOS E PRÁ

---

## 5. Pendências que este probe não resolve

| Pendência | Por quê | Próximo passo |
|---|---|---|
| **Número de licitantes por sessão** | Não existe campo na API do PNCP; só consta no PDF da ata | Parser best-effort sobre os arquivos, na Fase 3. Enquanto isso, os proxies (deserção, deságio, HHI) respondem a pergunta de negócio |
| **AUDESP Fase IV (TCE-SP)** | Cubos são arquivos para download, não REST; exigem inspeção manual do formato | Baixar um cubo de LICITACOES e verificar se traz contagem de participantes — resolveria a pendência acima de vez |
| **Cobertura de pregão presencial** | Depende do resultado da seção 2 | Se o caso-âncora falhou, priorizar AUDESP sobre qualquer outra fonte |
