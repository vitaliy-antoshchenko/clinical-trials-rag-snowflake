"""Exception hierarchy. The CLI turns any CtragError into a clean message and exit code 2."""


class CtragError(Exception):
    """Base class for expected, user-facing failures."""


class ConfigError(CtragError):
    """Missing or invalid configuration."""


class IngestError(CtragError):
    """The source registry returned something we cannot load."""


class GenerationError(CtragError):
    """The LLM call failed or returned an unexpected payload."""
