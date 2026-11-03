"""Private execution is opt-in, external-terminal-only; no account access at import."""

from .reports import validate_report
from .security import PrivateError

__all__ = ["PrivateError", "validate_report"]
