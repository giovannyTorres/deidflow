"""Local-first sensitive-data detection; no network or optional imports at import time."""

from deidflow.core import DocumentGraph, EntityType, Finding, Fragment, SourceLocation
from deidflow.domains import DomainPack, get_domain_pack, list_domain_packs
from deidflow.engine import DeidEngine, ReleaseStatus, Result
from deidflow.policies import Policy, Rule
from deidflow.session import DeidSession

__version__ = "0.6.0"
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
    "DomainPack",
    "get_domain_pack",
    "list_domain_packs",
    "DeidSession",
]
