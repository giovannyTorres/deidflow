"""Local-first sensitive-data detection; no network or optional imports at import time."""

from deidflow.core import DocumentGraph, EntityType, Finding, Fragment, SourceLocation
from deidflow.engine import DeidEngine, ReleaseStatus, Result
from deidflow.policies import Policy, Rule

__version__ = "0.2.0"
__all__ = [
    "DeidEngine",
    "Policy",
    "Rule",
    "Result",
    "ReleaseStatus",
    "Finding",
    "EntityType",
    "DocumentGraph",
    "Fragment",
    "SourceLocation",
]
