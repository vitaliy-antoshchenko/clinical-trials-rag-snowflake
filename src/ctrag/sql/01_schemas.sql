-- Three layers, one schema each:
--   RAW   source records exactly as delivered (VARIANT), replayable
--   CORE  normalised trial model, built from RAW with SQL only
--   RAG   retrieval chunks with embeddings, plus the question and answer audit log

CREATE SCHEMA IF NOT EXISTS RAW COMMENT = 'Source records exactly as delivered by ClinicalTrials.gov';
CREATE SCHEMA IF NOT EXISTS CORE COMMENT = 'Normalised trial model built from RAW with SQL';
CREATE SCHEMA IF NOT EXISTS RAG COMMENT = 'Retrieval chunks, embeddings and the audit log';

CREATE STAGE IF NOT EXISTS RAW.CTGOV_STAGE
    FILE_FORMAT = (TYPE = JSON)
    COMMENT = 'Landing zone for JSONL exports from the ClinicalTrials.gov API v2';

CREATE TABLE IF NOT EXISTS RAW.CTGOV_STUDIES (
    nct_id      STRING        NOT NULL,
    payload     VARIANT       NOT NULL,
    source_file STRING,
    loaded_at   TIMESTAMP_LTZ NOT NULL
);

-- Every answer is logged with the exact records it was grounded on.
CREATE TABLE IF NOT EXISTS RAG.QA_LOG (
    asked_at        TIMESTAMP_LTZ NOT NULL,
    question        STRING        NOT NULL,
    filters         VARIANT,
    retrieved       VARIANT,
    model           STRING,
    answer          STRING,
    citation_status STRING,
    citations       VARIANT,
    usage           VARIANT
);
