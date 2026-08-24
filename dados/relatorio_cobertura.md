# Relatório de cobertura — Fase 0

Gerado em 2026-08-24 00:43 UTC · 37 municípios-alvo

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

> **Atenção:** 2 de 7 endpoints não responderam como esperado. Os módulos que dependem deles degradam em vez de quebrar, mas a base ficará incompleta até que sejam corrigidos.

---

## 2. Teste de aceitação — Nova Castilho, Pregão Presencial 007/2026

É o único ponto do projeto com verdade conhecida de forma independente, extraída dos PDFs oficiais e registrada no handoff. Se o PNCP não contiver este pregão, a base não serve para pregão presencial de município pequeno — que é o padrão da região — e o cubo AUDESP do TCE-SP passa de complemento a peça obrigatória.

**Resultado: NÃO ENCONTRADO.**

Duas leituras possíveis, e a diferença entre elas decide o projeto:

1. O município não publicou este pregão no PNCP. Se for o caso, a cobertura de presencial é estruturalmente incompleta e o AUDESP Fase IV vira obrigatório.
2. Publicou, mas sob número, modalidade ou órgão diferentes do esperado. Confira a tabela de cobertura da seção 3 antes de concluir: se o município aparece com contratações no período, é este o caso.

---

## 3. Cobertura por município

Nenhuma contratação encontrada. Verifique a seção 1.

---

## 4. Mercado de serviço técnico em saúde

Contratações em dispensa, inexigibilidade e credenciamento cujo objeto classifica como serviço do domínio saúde. Dimensiona a segunda linha de negócio antes de qualquer investimento nela.

**Nenhuma contratação encontrada.** Duas leituras: o mercado local é pequeno demais, ou a taxonomia de `config/segmentos.yml` não está casando com o vocabulário dos editais da região. Antes de descartar a linha, revise os objetos brutos em `dados/probe.json`.

---

## 5. Pendências que este probe não resolve

| Pendência | Por quê | Próximo passo |
|---|---|---|
| **Número de licitantes por sessão** | Não existe campo na API do PNCP; só consta no PDF da ata | Parser best-effort sobre os arquivos, na Fase 3. Enquanto isso, os proxies (deserção, deságio, HHI) respondem a pergunta de negócio |
| **AUDESP Fase IV (TCE-SP)** | Cubos são arquivos para download, não REST; exigem inspeção manual do formato | Baixar um cubo de LICITACOES e verificar se traz contagem de participantes — resolveria a pendência acima de vez |
| **Cobertura de pregão presencial** | Depende do resultado da seção 2 | Se o caso-âncora falhou, priorizar AUDESP sobre qualquer outra fonte |
