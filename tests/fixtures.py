"""Dados do caso-âncora: Nova Castilho, Pregão Presencial 007/2026.

Os números vêm dos PDFs oficiais, registrados no handoff do projeto:
estimativa R$ 7,01/L, homologado R$ 6,92/L, 21.000 L em três itens,
ARP de R$ 145.320,00, um único licitante.

É o único ponto do projeto com verdade verificada de forma independente — por
isso serve de teste de regressão de toda a cadeia de coleta e cálculo.
"""

CNPJ_ORGAO = "01613202000171"
CONTROLE = f"{CNPJ_ORGAO}-1-000007/2026"
# Código confirmado pela API de Localidades do IBGE em 2026-08-24.
# Estava como "3532827", valor chutado ao escrever o fixture.
IBGE_NOVA_CASTILHO = "3532868"

ESTIMADO_UNITARIO = 7.01
HOMOLOGADO_UNITARIO = 6.92
QUANTIDADE_TOTAL = 21000
VALOR_TOTAL_ARP = 145320.00

# Fornecedor anonimizado: o teste só precisa de "um único licitante, porte EPP".
# O nome real não acrescenta nada à regressão e não precisa estar no repositório.
FORNECEDOR = {"ni": "00000000000191", "nome": "FORNECEDOR UNICO LTDA EPP", "porte": "EPP"}

CONTRATACAO = {
    "numeroControlePNCP": CONTROLE,
    "numeroCompra": "007/2026",
    "anoCompra": 2026,
    "sequencialCompra": 7,
    "processo": "030/2026",
    "modalidadeId": 7,
    "modalidadeNome": "Pregão - Presencial",
    "modoDisputaId": 4,
    "modoDisputaNome": "Menor Preço",
    "situacaoCompraId": 1,
    "situacaoCompraNome": "Divulgada no PNCP",
    "srp": True,
    "objetoCompra": "REGISTRO DE PRECOS PARA AQUISICAO DE LEITE PASTEURIZADO TIPO C INTEGRAL",
    "valorTotalEstimado": 147210.00,          # 21.000 L x R$ 7,01
    "valorTotalHomologado": VALOR_TOTAL_ARP,
    "dataPublicacaoPncp": "2026-07-07T10:00:00",
    "dataAberturaProposta": "2026-07-24T09:00:00",
    "dataEncerramentoProposta": "2026-07-24T09:30:00",
    "orgaoEntidade": {
        "cnpj": CNPJ_ORGAO,
        "razaoSocial": "MUNICIPIO DE NOVA CASTILHO",
        "esferaId": "M",
        "poderId": "E",
    },
    "unidadeOrgao": {
        "ufSigla": "SP",
        "municipioNome": "Nova Castilho",
        "codigoIbge": IBGE_NOVA_CASTILHO,
        "codigoUnidade": "1",
        "nomeUnidade": "PREFEITURA MUNICIPAL DE NOVA CASTILHO",
    },
    "amparoLegal": {"descricao": "Lei 14.133/2021, Art. 28, I"},
    "linkSistemaOrigem": "https://novacastilho.sp.gov.br/licitacao/007-2026",
}

# Três itens no Termo de Referência: duas escolas e a Assistência Social.
# Apenas 33% vai para escolas — o resto é programa social, não merenda.
_DESTINOS = [
    (1, "EMEI Adila Ana Conceicao dos Santos", 3000),
    (2, "EMEF Prof.a Sandra R. Feitosa Sobreira", 4000),
    (3, "Assistencia Social", 14000),
]

ITENS = [
    {
        "numeroItem": numero,
        "descricao": f"LEITE PASTEURIZADO TIPO C INTEGRAL - {destino}",
        "unidadeMedida": "LITRO",
        "quantidade": qtd,
        "valorUnitarioEstimado": ESTIMADO_UNITARIO,
        "valorTotal": round(qtd * ESTIMADO_UNITARIO, 2),
        "situacaoCompraItemId": 2,
        "situacaoCompraItemNome": "Homologado",
        "tipoBeneficioId": 4,
        "tipoBeneficioNome": "Sem benefício",
        "criterioJulgamentoNome": "Menor preço",
    }
    for numero, destino, qtd in _DESTINOS
]

RESULTADOS = {
    numero: [
        {
            "sequencialResultado": 1,
            "niFornecedor": FORNECEDOR["ni"],
            "nomeRazaoSocialFornecedor": FORNECEDOR["nome"],
            "porteFornecedorNome": FORNECEDOR["porte"],
            "quantidadeHomologada": qtd,
            "valorUnitarioHomologado": HOMOLOGADO_UNITARIO,
            "valorTotalHomologado": round(qtd * HOMOLOGADO_UNITARIO, 2),
            "dataResultado": "2026-07-29T10:30:00",
        }
    ]
    for numero, _destino, qtd in _DESTINOS
}

ARQUIVOS = [
    {"sequencialDocumento": 1, "titulo": "Edital Pregao 007-2026",
     "tipoDocumentoNome": "Edital", "url": "https://pncp.gov.br/arq/1"},
    {"sequencialDocumento": 2, "titulo": "Ata da Sessao Publica",
     "tipoDocumentoNome": "Ata", "url": "https://pncp.gov.br/arq/2"},
]


class PNCPFalso:
    """Dublê do cliente PNCP que devolve o caso-âncora e nada mais."""

    def __init__(self) -> None:
        self.falhas: list = []
        self.chamadas: list[str] = []

    def contratacoes_publicadas(self, codigo_ibge, modalidade, inicio, fim):
        self.chamadas.append(f"publicadas:{codigo_ibge}:{modalidade}")
        if codigo_ibge == IBGE_NOVA_CASTILHO and modalidade == 7:
            return [CONTRATACAO]
        return []

    def contratacoes_com_proposta_aberta(self, codigo_ibge, modalidade, data_final):
        return []

    def itens(self, cnpj, ano, sequencial):
        self.chamadas.append(f"itens:{cnpj}:{ano}:{sequencial}")
        return ITENS if cnpj == CNPJ_ORGAO else []

    def resultados(self, cnpj, ano, sequencial, item):
        return RESULTADOS.get(item, [])

    def arquivos(self, cnpj, ano, sequencial):
        return ARQUIVOS if cnpj == CNPJ_ORGAO else []

    def atas(self, inicio, fim, cnpj=None):
        return []

    def contratos(self, inicio, fim, cnpj_orgao=None):
        return []
