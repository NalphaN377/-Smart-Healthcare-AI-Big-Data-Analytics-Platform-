class AIError(Exception):
    """Base class for safe AI-layer failures."""


class ProviderNotConfigured(AIError):
    pass


class ProviderTimeout(AIError):
    pass


class ProviderFailure(AIError):
    pass


class UnsupportedQuery(AIError):
    pass


class ToolValidationFailure(AIError):
    pass

