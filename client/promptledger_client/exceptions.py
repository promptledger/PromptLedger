"""Exceptions raised by the PromptLedger client SDK."""


class PromptLedgerError(Exception):
    """Base exception for all PromptLedger client errors."""


class AuthError(PromptLedgerError):
    """Raised when the API key is missing or invalid (HTTP 401)."""


class NotFoundError(PromptLedgerError):
    """Raised when a requested resource does not exist (HTTP 404)."""
