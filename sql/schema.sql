-- Esquema da base de licitações.
--
-- Regra de estabilidade: coluna nova é sempre aditiva; coluna existente nunca é
-- removida nem renomeada. Os exports alimentam relatórios de BI externos, e
-- remover coluna quebra relatório silenciosamente.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------- dimensões

CREATE TABLE IF NOT EXISTS municipio (
    codigo_ibge            TEXT PRIMARY KEY,
    nome                   TEXT NOT NULL,
    uf                     TEXT NOT NULL,
    regiao_imediata        TEXT,
    regiao_intermediaria   TEXT,
    motivo_inclusao        TEXT,           -- regiao_imediata | extra
    prioritario            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orgao (
    cnpj            TEXT PRIMARY KEY,
    razao_social    TEXT,
    codigo_ibge     TEXT REFERENCES municipio(codigo_ibge),
    esfera          TEXT,
    poder           TEXT,
    de_saude        INTEGER NOT NULL DEFAULT 0   -- Fundo/Secretaria Municipal de Saúde
);

CREATE TABLE IF NOT EXISTS fornecedor (
    ni       TEXT PRIMARY KEY,              -- CNPJ ou CPF do fornecedor
    nome     TEXT,
    porte    TEXT
);

-- ------------------------------------------------------------------- fatos

CREATE TABLE IF NOT EXISTS contratacao (
    numero_controle_pncp        TEXT PRIMARY KEY,
    cnpj_orgao                  TEXT REFERENCES orgao(cnpj),
    codigo_ibge                 TEXT REFERENCES municipio(codigo_ibge),
    ano                         INTEGER,
    sequencial                  TEXT,
    numero_compra               TEXT,
    processo                    TEXT,
    modalidade_id               INTEGER,
    modalidade_nome             TEXT,
    presencial                  INTEGER NOT NULL DEFAULT 0,
    modo_disputa_id             INTEGER,
    modo_disputa_nome           TEXT,
    situacao_id                 INTEGER,
    situacao_nome               TEXT,
    srp                         INTEGER NOT NULL DEFAULT 0,   -- registro de preço
    objeto                      TEXT,
    valor_total_estimado        REAL,
    valor_total_homologado      REAL,
    data_publicacao             TEXT,
    data_abertura_proposta      TEXT,
    data_encerramento_proposta  TEXT,
    unidade_nome                TEXT,
    unidade_codigo              TEXT,
    orgao_de_saude              INTEGER NOT NULL DEFAULT 0,
    amparo_legal                TEXT,
    link_sistema_origem         TEXT,
    coletado_em                 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_contratacao_mun_ano ON contratacao(codigo_ibge, ano);
CREATE INDEX IF NOT EXISTS ix_contratacao_modalidade ON contratacao(modalidade_id);
CREATE INDEX IF NOT EXISTS ix_contratacao_encerramento ON contratacao(data_encerramento_proposta);

CREATE TABLE IF NOT EXISTS item (
    numero_controle_pncp        TEXT NOT NULL REFERENCES contratacao(numero_controle_pncp),
    numero_item                 INTEGER NOT NULL,
    descricao                   TEXT,
    unidade_medida              TEXT,
    quantidade                  REAL,
    valor_unitario_estimado     REAL,
    valor_total_estimado        REAL,
    situacao_item_id            INTEGER,     -- 4 = deserto, 5 = fracassado
    situacao_item_nome          TEXT,
    tipo_beneficio_id           INTEGER,     -- exclusividade / cota reservada ME-EPP
    tipo_beneficio_nome         TEXT,
    criterio_julgamento         TEXT,
    catmat                      TEXT,
    catser                      TEXT,
    -- classificação derivada (ver src/licita/segmentar.py)
    segmento                    TEXT,
    tipo_segmento               TEXT,        -- produto | servico
    dominio                     TEXT,
    aderencia                   TEXT,
    sinal_classificacao         TEXT,        -- catalogo | descricao | objeto | nenhum
    termo_classificacao         TEXT,
    coletado_em                 TEXT NOT NULL,
    PRIMARY KEY (numero_controle_pncp, numero_item)
);

CREATE INDEX IF NOT EXISTS ix_item_segmento ON item(segmento);
CREATE INDEX IF NOT EXISTS ix_item_situacao ON item(situacao_item_id);

CREATE TABLE IF NOT EXISTS resultado (
    numero_controle_pncp        TEXT NOT NULL,
    numero_item                 INTEGER NOT NULL,
    sequencial_resultado        INTEGER NOT NULL,
    ni_fornecedor               TEXT REFERENCES fornecedor(ni),
    nome_fornecedor             TEXT,
    porte_fornecedor            TEXT,
    quantidade_homologada       REAL,
    valor_unitario_homologado   REAL,
    valor_total_homologado      REAL,
    data_resultado              TEXT,
    coletado_em                 TEXT NOT NULL,
    PRIMARY KEY (numero_controle_pncp, numero_item, sequencial_resultado),
    FOREIGN KEY (numero_controle_pncp, numero_item)
        REFERENCES item(numero_controle_pncp, numero_item)
);

CREATE INDEX IF NOT EXISTS ix_resultado_fornecedor ON resultado(ni_fornecedor);

CREATE TABLE IF NOT EXISTS ata (
    numero_controle_pncp_ata     TEXT PRIMARY KEY,
    numero_controle_pncp_compra  TEXT,
    numero_ata                   TEXT,
    ano_ata                      INTEGER,
    cnpj_orgao                   TEXT,
    nome_orgao                   TEXT,
    codigo_ibge                  TEXT,
    objeto                       TEXT,
    data_assinatura              TEXT,
    vigencia_inicio              TEXT,
    vigencia_fim                 TEXT,
    cancelado                    INTEGER NOT NULL DEFAULT 0,
    data_cancelamento            TEXT,
    coletado_em                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ata_vigencia ON ata(vigencia_fim);

CREATE TABLE IF NOT EXISTS contrato (
    numero_controle_pncp        TEXT PRIMARY KEY,
    numero_contrato             TEXT,
    ano_contrato                INTEGER,
    cnpj_orgao                  TEXT,
    nome_orgao                  TEXT,
    codigo_ibge                 TEXT,
    ni_fornecedor               TEXT REFERENCES fornecedor(ni),
    nome_fornecedor             TEXT,
    objeto                      TEXT,
    valor_global                REAL,
    data_assinatura             TEXT,
    vigencia_inicio             TEXT,
    vigencia_fim                TEXT,
    data_publicacao             TEXT,
    segmento                    TEXT,
    tipo_segmento               TEXT,
    coletado_em                 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_contrato_fornecedor ON contrato(ni_fornecedor);
CREATE INDEX IF NOT EXISTS ix_contrato_mun ON contrato(codigo_ibge);

CREATE TABLE IF NOT EXISTS arquivo (
    numero_controle_pncp    TEXT NOT NULL,
    sequencial              INTEGER NOT NULL,
    titulo                  TEXT,
    tipo_documento          TEXT,
    url                     TEXT,
    data_publicacao         TEXT,
    coletado_em             TEXT NOT NULL,
    PRIMARY KEY (numero_controle_pncp, sequencial)
);

-- --------------------------------------------------------------- derivadas

-- Métricas de concorrência por município × segmento × ano.
CREATE TABLE IF NOT EXISTS metrica_mun_seg_ano (
    codigo_ibge              TEXT NOT NULL,
    segmento                 TEXT NOT NULL,
    ano                      INTEGER NOT NULL,
    tipo_segmento            TEXT,
    contratacoes             INTEGER NOT NULL DEFAULT 0,
    itens                    INTEGER NOT NULL DEFAULT 0,
    itens_homologados        INTEGER NOT NULL DEFAULT 0,
    itens_desertos           INTEGER NOT NULL DEFAULT 0,
    itens_fracassados        INTEGER NOT NULL DEFAULT 0,
    valor_estimado           REAL NOT NULL DEFAULT 0,
    valor_homologado         REAL NOT NULL DEFAULT 0,
    desagio_medio            REAL,          -- média do deságio por item, 0..1
    taxa_desercao            REAL,          -- (desertos + fracassados) / itens
    fornecedores_distintos   INTEGER NOT NULL DEFAULT 0,
    hhi                      REAL,          -- concentração de fornecedores, 0..1
    indice_oportunidade      REAL,          -- 0..100; maior = mais vácuo competitivo
    calculado_em             TEXT NOT NULL,
    PRIMARY KEY (codigo_ibge, segmento, ano)
);

-- Cobertura da fonte: quanto o PNCP realmente tem por município/ano/modalidade.
-- É o que responde se a base é confiável para pregão presencial de município pequeno.
CREATE TABLE IF NOT EXISTS cobertura (
    codigo_ibge      TEXT NOT NULL,
    ano              INTEGER NOT NULL,
    modalidade_id    INTEGER NOT NULL,
    contratacoes     INTEGER NOT NULL DEFAULT 0,
    itens            INTEGER NOT NULL DEFAULT 0,
    itens_com_resultado INTEGER NOT NULL DEFAULT 0,
    valor_estimado   REAL NOT NULL DEFAULT 0,
    coletado_em      TEXT NOT NULL,
    PRIMARY KEY (codigo_ibge, ano, modalidade_id)
);

-- Falhas de coleta, para o relatório saber o que ficou faltando e por quê.
CREATE TABLE IF NOT EXISTS coleta_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    execucao     TEXT NOT NULL,
    contexto     TEXT,
    url          TEXT,
    status       INTEGER,
    erro         TEXT,
    criado_em    TEXT NOT NULL
);

-- ------------------------------------------------------------------ visões

-- Item com tudo que o painel precisa, já desnormalizado.
CREATE VIEW IF NOT EXISTS v_item_completo AS
SELECT
    i.numero_controle_pncp,
    i.numero_item,
    m.codigo_ibge,
    m.nome                          AS municipio,
    m.prioritario                   AS municipio_prioritario,
    c.ano,
    c.numero_compra,
    c.modalidade_id,
    c.modalidade_nome,
    c.presencial,
    c.srp,
    c.situacao_nome                 AS situacao_contratacao,
    c.orgao_de_saude,
    c.objeto,
    c.data_publicacao,
    c.data_encerramento_proposta,
    c.link_sistema_origem,
    o.razao_social                  AS orgao,
    i.descricao,
    i.unidade_medida,
    i.quantidade,
    i.valor_unitario_estimado,
    i.valor_total_estimado,
    i.situacao_item_id,
    i.situacao_item_nome,
    i.tipo_beneficio_nome,
    i.segmento,
    i.tipo_segmento,
    i.dominio,
    i.aderencia,
    r.ni_fornecedor,
    r.nome_fornecedor,
    r.porte_fornecedor,
    r.valor_unitario_homologado,
    r.valor_total_homologado,
    CASE
        WHEN i.valor_unitario_estimado IS NULL OR i.valor_unitario_estimado <= 0
             OR r.valor_unitario_homologado IS NULL THEN NULL
        ELSE (i.valor_unitario_estimado - r.valor_unitario_homologado)
             / i.valor_unitario_estimado
    END                             AS desagio
FROM item i
JOIN contratacao c ON c.numero_controle_pncp = i.numero_controle_pncp
LEFT JOIN municipio m ON m.codigo_ibge = c.codigo_ibge
LEFT JOIN orgao o ON o.cnpj = c.cnpj_orgao
LEFT JOIN resultado r
       ON r.numero_controle_pncp = i.numero_controle_pncp
      AND r.numero_item = i.numero_item;

-- Oportunidades com proposta ainda em aberto.
CREATE VIEW IF NOT EXISTS v_radar AS
SELECT
    c.numero_controle_pncp,
    m.nome                AS municipio,
    m.prioritario         AS municipio_prioritario,
    c.numero_compra,
    c.modalidade_nome,
    c.presencial,
    c.objeto,
    c.valor_total_estimado,
    c.data_abertura_proposta,
    c.data_encerramento_proposta,
    c.orgao_de_saude,
    c.link_sistema_origem,
    o.razao_social        AS orgao
FROM contratacao c
LEFT JOIN municipio m ON m.codigo_ibge = c.codigo_ibge
LEFT JOIN orgao o ON o.cnpj = c.cnpj_orgao
WHERE c.data_encerramento_proposta IS NOT NULL
  AND date(substr(c.data_encerramento_proposta, 1, 10)) >= date('now');
