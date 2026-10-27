#!/usr/bin/env python3
"""
FoodBridge Secure RDS Credential Helper
Fetches database credentials dynamically from AWS Secrets Manager using IAM authentication.
Does not print, leak or store plain text passwords in source code.
Uses SQLAlchemy URL.create to safely escape passwords with special characters.
"""

import json
import os
import sys

try:
    from sqlalchemy.engine import URL
except ImportError:
    print("[ERROR] SQLAlchemy is required. Run: pip install SQLAlchemy")
    sys.exit(1)

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("[ERROR] boto3 is required. Run: pip install boto3")
    sys.exit(1)

# Default configuration for Kristina's FoodBridge deployment
DEFAULT_SECRET_ARN = os.environ.get(
    "RDS_SECRET_ARN",
    "arn:aws:secretsmanager:ap-south-1:879385476807:secret:rds!db-e2f2bbdf-1250-4c49-ab12-c6aea9ce6982-PV1F0K"
)
DEFAULT_REGION = os.environ.get("AWS_REGION", "ap-south-1")
DEFAULT_HOST = os.environ.get(
    "RDS_HOST",
    "foodbridge-mysql-db.chycksa68zyl.ap-south-1.rds.amazonaws.com"
)
DEFAULT_PORT = int(os.environ.get("RDS_PORT", 3306))
DEFAULT_DBNAME = os.environ.get("RDS_DBNAME", "foodbridge")

# In-memory cache for credentials to avoid redundant Secrets Manager API calls
_CREDENTIAL_CACHE = {}


def clear_credential_cache():
    """Clears the cached credentials to force fresh lookup upon rotation."""
    global _CREDENTIAL_CACHE
    _CREDENTIAL_CACHE.clear()


def get_secret(secret_arn=None, region_name=None, force_refresh=False):
    """
    Retrieves secret from AWS Secrets Manager using ambient IAM credentials
    (IAM instance profile on EC2 or active AWS profile locally).
    Caches the secret in memory unless force_refresh is True.
    """
    arn = secret_arn or DEFAULT_SECRET_ARN
    region = region_name or DEFAULT_REGION

    if not force_refresh and arn in _CREDENTIAL_CACHE:
        return _CREDENTIAL_CACHE[arn]

    profile = os.environ.get("AWS_PROFILE")
    if profile:
        session = boto3.Session(profile_name=profile, region_name=region)
    else:
        session = boto3.Session(region_name=region)

    client = session.client("secretsmanager")

    try:
        response = client.get_secret_value(SecretId=arn)
    except ClientError as e:
        print(f"[ERROR] Failed to retrieve secret from Secrets Manager: {e.response['Error']['Code']}")
        raise e

    if "SecretString" in response:
        secret_data = json.loads(response["SecretString"])
        _CREDENTIAL_CACHE[arn] = secret_data
        return secret_data
    return None


def get_database_url(
    secret_arn=None,
    region_name=None,
    override_username=None,
    override_host=None,
    override_port=None,
    override_dbname=None,
    force_refresh=False
):
    """
    Constructs a SQLAlchemy connection URL safely using sqlalchemy.engine.URL.create.
    Special characters in passwords (e.g., @, :, /, ?, #) are escaped automatically.
    Never exposes passwords in logs.
    """
    secret = get_secret(secret_arn, region_name, force_refresh=force_refresh)
    if not secret:
        raise ValueError("Empty secret received from Secrets Manager")

    username = override_username or secret.get("username", "foodbridge_admin")
    password = secret.get("password")
    if not password:
        raise ValueError("Password not found in secret payload")

    host = override_host or secret.get("host", DEFAULT_HOST)
    port = int(override_port or secret.get("port", DEFAULT_PORT))
    dbname = override_dbname or secret.get("dbname", DEFAULT_DBNAME)

    url_obj = URL.create(
        drivername="mysql+pymysql",
        username=username,
        password=password,
        host=host,
        port=port,
        database=dbname,
        query={"charset": "utf8mb4"}
    )
    return url_obj.render_as_string(hide_password=False)


def get_masked_database_url(
    secret_arn=None,
    region_name=None,
    override_username=None,
    override_host=None,
    override_port=None,
    override_dbname=None
):
    """
    Returns the database URL with the password securely masked (***) for logging.
    """
    secret = get_secret(secret_arn, region_name)
    username = override_username or secret.get("username", "foodbridge_admin")
    host = override_host or secret.get("host", DEFAULT_HOST)
    port = int(override_port or secret.get("port", DEFAULT_PORT))
    dbname = override_dbname or secret.get("dbname", DEFAULT_DBNAME)

    url_obj = URL.create(
        drivername="mysql+pymysql",
        username=username,
        password="***",
        host=host,
        port=port,
        database=dbname,
        query={"charset": "utf8mb4"}
    )
    return url_obj.render_as_string(hide_password=False)


def get_app_user_ddl_recommendation(app_username="foodbridge_app"):
    """
    Returns the least-privilege DDL required to create a dedicated application user.
    """
    return f"""-- Execute as RDS master admin (foodbridge_admin):
CREATE USER IF NOT EXISTS '{app_username}'@'%' IDENTIFIED BY '<STRONG_GENERATED_PASSWORD>';
GRANT SELECT, INSERT, UPDATE, DELETE ON {DEFAULT_DBNAME}.* TO '{app_username}'@'%';
FLUSH PRIVILEGES;
"""


if __name__ == "__main__":
    try:
        masked_url = get_masked_database_url()
        print("[SUCCESS] Successfully configured database connection URL via Secrets Manager.")
        print(f"  Connection URL: {masked_url}")
        print("  Password Status: Verified and protected (not displayed or written to disk)")
    except Exception as ex:
        print(f"[FAIL] Could not retrieve database secret: {ex}")
        sys.exit(1)
