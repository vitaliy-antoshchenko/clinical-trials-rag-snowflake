-- Full refresh of the raw layer from the file uploaded to the stage.
-- docs/architecture.md describes the incremental version (MERGE on nct_id + last update date).

TRUNCATE TABLE RAW.CTGOV_STUDIES;

COPY INTO RAW.CTGOV_STUDIES (nct_id, payload, source_file, loaded_at)
FROM (
    SELECT
        $1:protocolSection:identificationModule:nctId::STRING,
        $1,
        METADATA$FILENAME,
        CURRENT_TIMESTAMP()
    FROM @RAW.CTGOV_STAGE
)
FILE_FORMAT = (TYPE = JSON)
ON_ERROR = ABORT_STATEMENT
FORCE = TRUE;
