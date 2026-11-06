"""Versioned, local Spanish domain packs with explicit operating choices.

A pack binds rules, a pinned discriminative model and a context policy. It is not
a certification of anonymity: packaged benchmarks do not establish quality on
the user's documents, and legal is a general-model starter, not a legal model.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from deidflow.core import EntityType
from deidflow.detectors import CORE_RULES_VERSION
from deidflow.detectors.domain_roles import (
    DOMAIN_RULES_VERSION,
    DomainModelAdapter,
    DomainRoleRecognizer,
)
from deidflow.detectors.narrative import NarrativeRecognizer
from deidflow.engine import DeidEngine
from deidflow.nlp.tagger import BUILTIN_MODELS, SpanTagger, builtin_profiles
from deidflow.policies import Policy, Rule

if TYPE_CHECKING:
    from deidflow.session import DeidSession

_CLINICAL_CONTEXT = (
    "DIAGNOSIS",
    "MEDICAL_CONDITION",
    "TREATMENT",
    "MEDICATION",
    "CLINICAL_OBSERVATION",
    "MEDICAL_HISTORY",
    "MEDICAL_ATTRIBUTE",
)
_PRESERVED = (*_CLINICAL_CONTEXT, "DEMOGRAPHIC", "AMOUNT")
_KNOWN_TYPES = frozenset(str(kind) for kind in EntityType) | {"AMOUNT"}
_COMMON_LIMITATIONS = (
    "Supervised use: evaluate with representative local documents and review before release.",
    "Rules and models can miss identifiers or remove useful context; scores are not calibrated probabilities.",
    "Amounts and clinical content are kept by policy only when detected with the correct category; ambiguous overlaps retain identifier protection.",
    "Exact-name consistency is scoped to a session; aliases, pronouns and relationships are not inferred.",
    "Absolute dates and ages remain quasi-identifiers and are indexed by default; numeric date shifts are explicit opt-ins.",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class DomainPack:
    """Immutable metadata and factories for one version of a Spanish workflow."""

    name: str
    version: str
    title: str
    model_name: str
    model_sha256: str
    training_corpus: tuple[str, ...]
    training_license: tuple[str, ...]
    evaluation_scope: str
    roles: tuple[str, ...]
    limitations: tuple[str, ...]
    language: str = "es"
    code_license: str = "Apache-2.0"
    model_card: str = "docs/TAGGER.md"
    preserved_types: tuple[str, ...] = _PRESERVED
    supervised_review: bool = True
    detector_version: str = DOMAIN_RULES_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe metadata, including pinned provenance and limitations."""
        return json.loads(json.dumps(asdict(self)))

    def fingerprint(self) -> str:
        return _digest(self.to_dict())

    def policy(
        self,
        *,
        preserve_context: bool = True,
        sensitive_types: Iterable[str] = (),
        verify_proper_nouns: bool = True,
        dates: str = "indexed",
        shift_days: int = 0,
    ) -> Policy:
        """Index identifiers while preserving explicitly categorized useful context.

        ``sensitive_types`` overrides preservation (for example ``MEDICATION`` or
        ``AMOUNT``). Absolute dates default to indexed tokens. ``dates='shift'``
        requires a nonzero, fixed offset and allows only DATE residuals from the
        shift. DATE_OF_BIRTH remains indexed for every date option.
        """
        if type(preserve_context) is not bool or type(verify_proper_nouns) is not bool:
            raise ValueError("Context and verification options must be booleans")
        if isinstance(sensitive_types, (str, bytes)):
            raise ValueError("sensitive_types must be a sequence of entity categories")
        sensitive = tuple(sensitive_types)
        if any(not isinstance(kind, str) or kind not in _KNOWN_TYPES for kind in sensitive):
            raise ValueError("Unknown sensitive entity category")
        if dates not in {"indexed", "keep", "shift"}:
            raise ValueError("dates must be indexed, keep or shift")
        if type(shift_days) is not int or abs(shift_days) > 36500:
            raise ValueError("Invalid date shift")
        if (dates == "shift" and shift_days == 0) or (dates != "shift" and shift_days != 0):
            raise ValueError("A nonzero shift_days is required only for dates='shift'")
        entities = {kind: Rule("keep") for kind in self.preserved_types} if preserve_context else {}
        if dates == "keep":
            entities["DATE"] = Rule("keep")
        elif dates == "shift":
            entities["DATE"] = Rule("date_shift", shift_days=shift_days)
        entities.update({kind: Rule("indexed") for kind in sensitive})
        entities["DATE_OF_BIRTH"] = Rule("indexed")
        return Policy(
            name=f"domain:{self.name}@{self.version}",
            default=Rule("indexed"),
            entities=entities,
            require_ner=True,
            require_human_review=True,
            review_below=0.75,
            token_scope="session",
            independent_check="proper_nouns" if verify_proper_nouns else "none",
            allow_residual_types=("DATE",) if dates == "shift" and "DATE" not in sensitive else (),
        )

    def recognizers(self) -> tuple[NarrativeRecognizer, DomainRoleRecognizer]:
        """Create fresh additive rules; no rule suppresses an identifier finding."""
        return NarrativeRecognizer(), DomainRoleRecognizer(self.name)

    def engine(
        self,
        *,
        model: str = "default",
        profile: str = "balanced",
        country: str | Iterable[str] = "ALL",
        adapter: Any = None,
        adapter_digest: str | None = None,
    ) -> DeidEngine:
        """Create a local engine with explicit model selection.

        ``default``/``builtin`` load the pack's pinned packaged model. ``rules``
        omits statistical NLP and therefore requires review under the pack policy.
        ``custom`` accepts a trusted local detect_batch adapter and an explicitly
        supplied SHA-256 identifying its assets/configuration. That digest is a
        caller assertion, not verification of arbitrary Python adapter code.
        """
        if model not in {"default", "builtin", "rules", "custom"}:
            raise ValueError("model must be default, builtin, rules or custom")
        if profile not in {"balanced", "assurance"}:
            raise ValueError("profile must be balanced or assurance")
        if model != "custom" and (adapter is not None or adapter_digest is not None):
            raise ValueError("Adapters and adapter_digest require model='custom'")
        settings: dict[str, Any] = {}
        if model in {"default", "builtin"}:
            pinned = BUILTIN_MODELS.get(self.model_name)
            if pinned is None or pinned[1] != self.model_sha256:
                raise ValueError("Domain pack model pin does not match packaged model registry")
            settings = builtin_profiles()[self.model_name][profile]
            nlp: Any = SpanTagger.builtin(self.model_name, profile=profile)
            selected = self.model_name
            asset_digest: str | None = self.model_sha256
        elif model == "custom":
            if not callable(getattr(adapter, "detect_batch", None)):
                raise ValueError("A local detect_batch adapter is required for model='custom'")
            if not isinstance(adapter_digest, str) or not re.fullmatch(
                r"[0-9a-f]{64}", adapter_digest
            ):
                raise ValueError(
                    "Custom adapters require an explicit lowercase SHA-256 adapter_digest"
                )
            if profile != "balanced":
                raise ValueError(
                    "Custom adapter operating thresholds must be configured on the adapter"
                )
            nlp, selected, asset_digest = adapter, "custom", adapter_digest
        else:
            nlp, selected, asset_digest = None, "rules", None
        if nlp is not None:
            nlp = DomainModelAdapter(nlp, self.name)
        engine = DeidEngine(
            language=self.language,
            country=country,
            nlp=nlp,
            recognizers=self.recognizers(),
            performance=profile,
        )
        # Bound to the pack/rules, asset, operating profile and country selection.
        # The session also authenticates the separate policy fingerprint.
        engine_digest = _digest(
            {
                "pack": self.fingerprint(),
                "model": selected,
                "asset_sha256": asset_digest,
                "profile": profile,
                "operating_settings": settings,
                "countries": sorted(engine.countries) if engine.countries is not None else "ALL",
                "detectors": (DOMAIN_RULES_VERSION, "narrative-0.5", CORE_RULES_VERSION),
            }
        )
        engine.model_digest = engine_digest
        return engine

    def session(
        self,
        *,
        model: str = "default",
        profile: str = "balanced",
        country: str | Iterable[str] = "ALL",
        adapter: Any = None,
        adapter_digest: str | None = None,
        policy: Policy | None = None,
        reversible: bool = True,
    ) -> DeidSession:
        """Create an independent neutral session using this pack's default policy."""
        from deidflow.session import DeidSession

        engine = self.engine(
            model=model,
            profile=profile,
            country=country,
            adapter=adapter,
            adapter_digest=adapter_digest,
        )
        return DeidSession(
            engine,
            policy=self.policy() if policy is None else policy,
            reversible=reversible,
            model_digest=engine.model_digest,
        )


_PACKS = (
    DomainPack(
        name="clinical",
        version="1.0.0",
        title="Clínico en español",
        model_name="es-clinical",
        model_sha256="dc824100552ddb5bae036d128da9cfe4e31aba68b7cb74c2ab1252ddc0952da9",
        training_corpus=(
            "MEDDOCAN train, commit 783a6df385c975b328c99bcffb54196a9ba4078a: clinical text with synthetic PHI",
        ),
        training_license=("CC-BY-4.0; attribution in NOTICE",),
        evaluation_scope="MEDDOCAN Spain held-out documents; not validation on local clinical records.",
        roles=("patient", "clinician", "family"),
        limitations=(
            *_COMMON_LIMITATIONS,
            "Clinical preservation is utility-oriented; rare diagnoses and combinations can re-identify a person.",
        ),
    ),
    DomainPack(
        name="financial",
        version="1.0.0",
        title="Financiero en español",
        model_name="es-finance",
        model_sha256="f7a28b8fef3ccc1090d171b693f744098b4032008a48b56530c5aabdf371679c",
        training_corpus=(
            "Gretel synthetic_pii_finance_multilingual, revision 7b844d16738527a04264f50214cb426a4cea0897, Spanish train minus 10% holdout",
        ),
        training_license=("Apache-2.0; attribution in NOTICE",),
        evaluation_scope="Synthetic Gretel Spanish holdout; not validation on banking customer records.",
        roles=("customer", "creditor", "debtor", "agent"),
        limitations=(
            *_COMMON_LIMITATIONS,
            "Financial models have known residual misses; amounts may be confidential or uniquely identifying.",
        ),
    ),
    DomainPack(
        name="legal",
        version="1.0.0",
        title="Jurídico en español (inicial)",
        model_name="es-general",
        model_sha256="bf7e257f363e17bcc6bee943f9dfaa0cd67e502cf8ac3fd90140bdd916a51903",
        training_corpus=(
            "MEDDOCAN train, commit 783a6df385c975b328c99bcffb54196a9ba4078a",
            "Gretel Spanish train minus holdout, revision 7b844d16738527a04264f50214cb426a4cea0897",
            "deidflow.benchmarks.synthetic_es: 3000 documents, seed 1729, Faker 40.44.0",
        ),
        training_license=(
            "CC-BY-4.0 (MEDDOCAN)",
            "Apache-2.0 (Gretel and project generator)",
            "MIT (Faker); attribution in NOTICE",
        ),
        evaluation_scope="General-model held-out clinical/financial/synthetic layouts; no independent legal-domain validation.",
        roles=("plaintiff", "defendant", "witness", "lawyer", "judge"),
        limitations=(
            *_COMMON_LIMITATIONS,
            "Starter: general model plus explicit legal-role rules, not a trained or validated specialist legal model.",
            "Clauses and negations remain text; this pack does not interpret obligations or infer legal relationships.",
        ),
    ),
    DomainPack(
        name="general",
        version="1.0.0",
        title="General en español",
        model_name="es-general",
        model_sha256="bf7e257f363e17bcc6bee943f9dfaa0cd67e502cf8ac3fd90140bdd916a51903",
        training_corpus=(
            "MEDDOCAN train, commit 783a6df385c975b328c99bcffb54196a9ba4078a",
            "Gretel Spanish train minus holdout, revision 7b844d16738527a04264f50214cb426a4cea0897",
            "deidflow.benchmarks.synthetic_es: 3000 documents, seed 1729, Faker 40.44.0",
        ),
        training_license=(
            "CC-BY-4.0 (MEDDOCAN)",
            "Apache-2.0 (Gretel and project generator)",
            "MIT (Faker); attribution in NOTICE",
        ),
        evaluation_scope="Held-out MEDDOCAN/Gretel and synthetic template families; not real-world country/domain validation.",
        roles=(
            "patient",
            "clinician",
            "family",
            "customer",
            "creditor",
            "debtor",
            "agent",
            "plaintiff",
            "defendant",
            "witness",
            "lawyer",
            "judge",
        ),
        limitations=(
            *_COMMON_LIMITATIONS,
            "Synthetic cross-country layouts do not establish recall on real documents from those countries.",
        ),
    ),
)


def list_domain_packs() -> tuple[DomainPack, ...]:
    """List installed packs deterministically without loading model weights."""
    return _PACKS


def get_domain_pack(name: str, *, version: str | None = None) -> DomainPack:
    """Select an installed name/version, accepting ``name@version`` for pinning."""
    if not isinstance(name, str) or not name:
        raise ValueError("A domain pack name is required")
    if "@" in name:
        name, inline_version = name.split("@", 1)
        if version is not None and version != inline_version:
            raise ValueError("Conflicting domain pack versions")
        version = inline_version
    for pack in _PACKS:
        if pack.name == name and (version is None or version == pack.version):
            return pack
    raise ValueError(
        "Unknown domain pack or version; installed: " + ", ".join(p.name for p in _PACKS)
    )


__all__ = ["DomainPack", "get_domain_pack", "list_domain_packs"]
