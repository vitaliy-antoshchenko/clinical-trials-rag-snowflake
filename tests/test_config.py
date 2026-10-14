from pathlib import Path

import pytest

from ctrag.config import DEFAULT_EMBED_MODEL, load_settings
from ctrag.errors import ConfigError

REQUIRED = {
    "SNOWFLAKE_ACCOUNT": "org-acct",
    "SNOWFLAKE_USER": "CTRAG_SVC",
    "SNOWFLAKE_PRIVATE_KEY_PATH": "~/keys/rsa_key.p8",
}


def test_defaults_fill_optional_values() -> None:
    settings = load_settings(REQUIRED)
    assert settings.snowflake.role == "CTRAG_ROLE"
    assert settings.snowflake.database == "CTRAG"
    assert settings.embed_model == DEFAULT_EMBED_MODEL
    assert settings.top_k == 8
    assert settings.snowflake.private_key_path == Path("~/keys/rsa_key.p8").expanduser()


@pytest.mark.parametrize("missing", sorted(REQUIRED))
def test_missing_required_value_is_a_config_error(missing: str) -> None:
    env = {k: v for k, v in REQUIRED.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        load_settings(env)


@pytest.mark.parametrize("value", ["abc", "0", "500"])
def test_top_k_is_validated(value: str) -> None:
    with pytest.raises(ConfigError, match="CTRAG_TOP_K"):
        load_settings({**REQUIRED, "CTRAG_TOP_K": value})
