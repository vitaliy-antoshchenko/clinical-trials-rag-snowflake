-- CORE: a normalised model of each trial, parsed from the raw JSON inside Snowflake.
-- Tables are rebuilt from RAW on every run, so RAW stays the single source of truth.
-- Grain: STUDIES one row per trial, the rest one row per list item of that trial.

CREATE OR REPLACE VIEW CORE.LATEST_RAW AS
SELECT
    nct_id,
    payload:protocolSection AS p,
    payload:derivedSection  AS d,
    payload:hasResults::BOOLEAN AS has_results,
    loaded_at
FROM RAW.CTGOV_STUDIES
QUALIFY ROW_NUMBER() OVER (PARTITION BY nct_id ORDER BY loaded_at DESC) = 1;

CREATE OR REPLACE TABLE CORE.STUDIES AS
SELECT
    r.nct_id,
    r.p:identificationModule:briefTitle::STRING    AS brief_title,
    r.p:identificationModule:officialTitle::STRING AS official_title,
    r.p:identificationModule:acronym::STRING       AS acronym,
    r.p:statusModule:overallStatus::STRING         AS overall_status,
    r.p:designModule:studyType::STRING             AS study_type,
    COALESCE(r.p:designModule:phases::ARRAY, ARRAY_CONSTRUCT()) AS phases,
    NULLIF(ARRAY_TO_STRING(COALESCE(r.p:designModule:phases::ARRAY, ARRAY_CONSTRUCT()), '/'), '')
                                                   AS phase_label,
    r.p:designModule:designInfo:allocation::STRING          AS allocation,
    r.p:designModule:designInfo:interventionModel::STRING   AS intervention_model,
    r.p:designModule:designInfo:primaryPurpose::STRING      AS primary_purpose,
    r.p:designModule:designInfo:maskingInfo:masking::STRING AS masking,
    r.p:designModule:enrollmentInfo:count::INT              AS enrollment_count,
    r.p:designModule:enrollmentInfo:type::STRING            AS enrollment_type,
    COALESCE(
        TRY_TO_DATE(r.p:statusModule:startDateStruct:date::STRING, 'YYYY-MM-DD'),
        TRY_TO_DATE(r.p:statusModule:startDateStruct:date::STRING, 'YYYY-MM')
    ) AS start_date,
    COALESCE(
        TRY_TO_DATE(r.p:statusModule:primaryCompletionDateStruct:date::STRING, 'YYYY-MM-DD'),
        TRY_TO_DATE(r.p:statusModule:primaryCompletionDateStruct:date::STRING, 'YYYY-MM')
    ) AS primary_completion_date,
    TRY_TO_DATE(r.p:statusModule:lastUpdatePostDateStruct:date::STRING, 'YYYY-MM-DD')
        AS last_update_date,
    r.p:sponsorCollaboratorsModule:leadSponsor:name::STRING  AS lead_sponsor,
    r.p:sponsorCollaboratorsModule:leadSponsor:class::STRING AS lead_sponsor_class,
    r.has_results,
    r.p:descriptionModule:briefSummary::STRING        AS brief_summary,
    r.p:descriptionModule:detailedDescription::STRING AS detailed_description,
    'https://clinicaltrials.gov/study/' || r.nct_id   AS registry_url
FROM CORE.LATEST_RAW r;

CREATE OR REPLACE TABLE CORE.CONDITIONS AS
SELECT r.nct_id, c.value::STRING AS condition, NULL::STRING AS mesh_id, 'reported' AS source,
       c.index AS ordinal
FROM CORE.LATEST_RAW r, LATERAL FLATTEN(input => r.p:conditionsModule:conditions) c
UNION ALL
SELECT r.nct_id, m.value:term::STRING, m.value:id::STRING, 'mesh', m.index
FROM CORE.LATEST_RAW r, LATERAL FLATTEN(input => r.d:conditionBrowseModule:meshes) m;

CREATE OR REPLACE TABLE CORE.INTERVENTIONS AS
SELECT
    r.nct_id,
    i.index                                                    AS ordinal,
    i.value:type::STRING                                       AS intervention_type,
    i.value:name::STRING                                       AS name,
    i.value:description::STRING                                AS description,
    COALESCE(i.value:otherNames::ARRAY, ARRAY_CONSTRUCT())     AS other_names,
    COALESCE(i.value:armGroupLabels::ARRAY, ARRAY_CONSTRUCT()) AS arm_group_labels
FROM CORE.LATEST_RAW r, LATERAL FLATTEN(input => r.p:armsInterventionsModule:interventions) i;

CREATE OR REPLACE TABLE CORE.ARMS AS
SELECT
    r.nct_id,
    a.index                                                       AS ordinal,
    a.value:label::STRING                                         AS label,
    a.value:type::STRING                                          AS arm_type,
    a.value:description::STRING                                   AS description,
    COALESCE(a.value:interventionNames::ARRAY, ARRAY_CONSTRUCT()) AS intervention_names
FROM CORE.LATEST_RAW r, LATERAL FLATTEN(input => r.p:armsInterventionsModule:armGroups) a;

CREATE OR REPLACE TABLE CORE.OUTCOMES AS
SELECT r.nct_id, 'PRIMARY' AS outcome_type, o.index AS ordinal,
       o.value:measure::STRING AS measure, o.value:description::STRING AS description,
       o.value:timeFrame::STRING AS time_frame
FROM CORE.LATEST_RAW r, LATERAL FLATTEN(input => r.p:outcomesModule:primaryOutcomes) o
UNION ALL
SELECT r.nct_id, 'SECONDARY', o.index,
       o.value:measure::STRING, o.value:description::STRING, o.value:timeFrame::STRING
FROM CORE.LATEST_RAW r, LATERAL FLATTEN(input => r.p:outcomesModule:secondaryOutcomes) o;

-- Inclusion and exclusion criteria are one free-text field in the registry. They are split here
-- because "who can join" and "who is ruled out" are different questions at retrieval time.
CREATE OR REPLACE TABLE CORE.ELIGIBILITY AS
WITH criteria AS (
    SELECT
        r.nct_id,
        r.p:eligibilityModule AS m,
        r.p:eligibilityModule:eligibilityCriteria::STRING AS criteria_text
    FROM CORE.LATEST_RAW r
),
split AS (
    SELECT
        nct_id, m, criteria_text,
        REGEXP_INSTR(criteria_text, 'exclusion criteria', 1, 1, 0, 'i') AS exclusion_pos
    FROM criteria
)
SELECT
    nct_id,
    criteria_text,
    TRIM(IFF(exclusion_pos > 0, SUBSTR(criteria_text, 1, exclusion_pos - 1), criteria_text))
        AS inclusion_text,
    IFF(exclusion_pos > 0, TRIM(SUBSTR(criteria_text, exclusion_pos)), NULL) AS exclusion_text,
    m:sex::STRING                                  AS sex,
    m:minimumAge::STRING                           AS minimum_age,
    m:maximumAge::STRING                           AS maximum_age,
    m:healthyVolunteers::BOOLEAN                   AS healthy_volunteers,
    COALESCE(m:stdAges::ARRAY, ARRAY_CONSTRUCT())  AS std_ages
FROM split;

CREATE OR REPLACE TABLE CORE.SITES AS
SELECT
    r.nct_id,
    l.index                       AS ordinal,
    l.value:facility::STRING      AS facility,
    l.value:city::STRING          AS city,
    l.value:state::STRING         AS state,
    l.value:country::STRING       AS country,
    l.value:status::STRING        AS recruitment_status,
    l.value:geoPoint:lat::FLOAT   AS latitude,
    l.value:geoPoint:lon::FLOAT   AS longitude
FROM CORE.LATEST_RAW r, LATERAL FLATTEN(input => r.p:contactsLocationsModule:locations) l;
