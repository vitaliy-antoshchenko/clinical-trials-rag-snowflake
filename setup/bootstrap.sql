-- One-time account setup. Run as ACCOUNTADMIN in a Snowsight worksheet.
--
-- Creates a least-privilege role, an extra-small auto-suspending warehouse, the CTRAG database and
-- a service user that signs in with a key pair. Generate the key pair locally first:
--
--   openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
--   openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
--
-- and paste the body of rsa_key.pub (without the BEGIN/END lines) below.

USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS CTRAG_ROLE;
-- Custom roles roll up to SYSADMIN, so admins can see and manage what the app creates.
GRANT ROLE CTRAG_ROLE TO ROLE SYSADMIN;

CREATE WAREHOUSE IF NOT EXISTS CTRAG_WH
    WAREHOUSE_SIZE = XSMALL
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;

CREATE DATABASE IF NOT EXISTS CTRAG;
GRANT OWNERSHIP ON DATABASE CTRAG TO ROLE CTRAG_ROLE;
GRANT USAGE ON WAREHOUSE CTRAG_WH TO ROLE CTRAG_ROLE;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE CTRAG_ROLE;

CREATE USER IF NOT EXISTS CTRAG_SVC
    TYPE = SERVICE
    DEFAULT_ROLE = CTRAG_ROLE
    DEFAULT_WAREHOUSE = CTRAG_WH
    RSA_PUBLIC_KEY = '<paste public key body here>';
GRANT ROLE CTRAG_ROLE TO USER CTRAG_SVC;

-- Value for SNOWFLAKE_ACCOUNT in .env
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS account_identifier;
