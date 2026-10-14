-- RAG: retrieval-ready text built from CORE.
-- Each trial becomes up to five sections by meaning (overview, treatment, inclusion, exclusion,
-- outcomes). Each section is then split by length. Every chunk starts with a header naming the
-- trial, phase and status, and carries phases, status and conditions as columns, so filters run
-- in SQL before any vector ranking.

CREATE OR REPLACE TABLE RAG.SECTIONS AS
WITH conditions AS (
    SELECT
        nct_id,
        ARRAY_AGG(DISTINCT LOWER(condition)) AS conditions,
        LISTAGG(DISTINCT IFF(source = 'reported', condition, NULL), '; ') AS condition_label
    FROM CORE.CONDITIONS
    GROUP BY nct_id
),
arms AS (
    SELECT
        nct_id,
        LISTAGG(
            'Arm ' || COALESCE(label, 'unnamed') || ' (' || COALESCE(arm_type, 'type n/a') || '):'
            || COALESCE(' ' || RTRIM(description, '. ') || '.', '')
            || IFF(ARRAY_SIZE(intervention_names) > 0,
                   ' Interventions: ' || ARRAY_TO_STRING(intervention_names, ', ') || '.', ''),
            '\n'
        ) WITHIN GROUP (ORDER BY ordinal) AS arms_text
    FROM CORE.ARMS
    GROUP BY nct_id
),
interventions AS (
    SELECT
        nct_id,
        LISTAGG(
            COALESCE(intervention_type, 'OTHER') || ' ' || COALESCE(name, '')
            || COALESCE(': ' || description, ''),
            '\n'
        ) WITHIN GROUP (ORDER BY ordinal) AS interventions_text,
        LISTAGG(name, ', ') WITHIN GROUP (ORDER BY ordinal) AS intervention_names
    FROM CORE.INTERVENTIONS
    GROUP BY nct_id
),
outcomes AS (
    SELECT
        nct_id,
        LISTAGG(
            INITCAP(outcome_type) || ' outcome: ' || COALESCE(measure, '')
            || COALESCE(' (time frame: ' || time_frame || ')', '')
            || COALESCE('. ' || description, ''),
            '\n'
        ) WITHIN GROUP (ORDER BY outcome_type, ordinal) AS outcomes_text
    FROM CORE.OUTCOMES
    GROUP BY nct_id
),
base AS (
    SELECT
        s.*,
        c.conditions, c.condition_label,
        a.arms_text,
        i.interventions_text, i.intervention_names,
        o.outcomes_text,
        e.inclusion_text, e.exclusion_text, e.sex, e.minimum_age, e.maximum_age
    FROM CORE.STUDIES s
    LEFT JOIN conditions    c ON c.nct_id = s.nct_id
    LEFT JOIN arms          a ON a.nct_id = s.nct_id
    LEFT JOIN interventions i ON i.nct_id = s.nct_id
    LEFT JOIN outcomes      o ON o.nct_id = s.nct_id
    LEFT JOIN CORE.ELIGIBILITY e ON e.nct_id = s.nct_id
),
sections AS (
    SELECT
        nct_id,
        'overview' AS section,
        brief_title || '.' || COALESCE(' ' || official_title || '.', '')
        || '\nSponsor: ' || COALESCE(lead_sponsor, 'n/a')
        || '. Design: ' || COALESCE(primary_purpose, 'n/a')
        || ', allocation ' || COALESCE(allocation, 'n/a')
        || ', masking ' || COALESCE(masking, 'n/a')
        || ', planned enrollment ' || COALESCE(enrollment_count::STRING, 'n/a') || '.'
        || COALESCE('\nInterventions: ' || intervention_names || '.', '')
        || COALESCE('\nSummary: ' || brief_summary, '') AS section_text
    FROM base
    UNION ALL
    SELECT nct_id, 'treatment',
           NULLIF(TRIM(COALESCE(arms_text, '') || '\n' || COALESCE(interventions_text, '')), '')
    FROM base
    UNION ALL
    SELECT nct_id, 'eligibility_inclusion',
           inclusion_text
           || '\nSex: ' || COALESCE(sex, 'n/a')
           || '. Age: ' || COALESCE(minimum_age, 'n/a') || ' to ' || COALESCE(maximum_age, 'no upper limit') || '.'
    FROM base
    UNION ALL
    SELECT nct_id, 'eligibility_exclusion', exclusion_text FROM base
    UNION ALL
    SELECT nct_id, 'outcomes', outcomes_text FROM base
)
SELECT
    sec.nct_id,
    sec.section,
    'Trial ' || b.nct_id || ' | ' || b.brief_title
        || ' | Phase: ' || COALESCE(b.phase_label, 'not applicable')
        || ' | Status: ' || COALESCE(b.overall_status, 'unknown')
        || COALESCE(' | Conditions: ' || b.condition_label, '')
        || ' | Section: ' || sec.section AS header,
    sec.section_text,
    b.phases,
    b.overall_status,
    COALESCE(b.conditions, ARRAY_CONSTRUCT()) AS conditions
FROM sections sec
JOIN base b ON b.nct_id = sec.nct_id
WHERE sec.section_text IS NOT NULL AND LENGTH(TRIM(sec.section_text)) > 0;

-- Split by length (about 1,400 characters, 150 overlap: inside the embedding model's input limit),
-- then embed with Cortex. The vectors never leave the account.
CREATE OR REPLACE TABLE RAG.CHUNKS AS
WITH pieces AS (
    SELECT
        s.nct_id, s.section, s.phases, s.overall_status, s.conditions,
        f.index AS chunk_index,
        s.header || '\n' || f.value::STRING AS chunk_text
    FROM RAG.SECTIONS s,
         LATERAL FLATTEN(
             input => SNOWFLAKE.CORTEX.SPLIT_TEXT_RECURSIVE_CHARACTER(s.section_text, 'none', 1400, 150)
         ) f
    -- The splitter leaves short fragments such as "Exclusion criteria are fulfilled:". As chunks
    -- they are almost all header, rank well on title words and give the model nothing to use.
    WHERE LENGTH(TRIM(f.value::STRING)) >= 120
)
SELECT
    nct_id || ':' || section || ':' || chunk_index AS chunk_id,
    nct_id,
    section,
    chunk_index,
    phases,
    overall_status,
    conditions,
    chunk_text,
    SNOWFLAKE.CORTEX.EMBED_TEXT_768('{{embed_model}}', chunk_text) AS embedding
FROM pieces;
