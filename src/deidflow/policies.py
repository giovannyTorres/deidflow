"""Strict, versionable configuration; categories are independent of actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any

ACTIONS = frozenset(
    {
        "redact",
        "placeholder",
        "indexed",
        "pseudonym",
        "generalize",
        "suppress",
        "date_shift",
        "bucket",
        "mask",
        "keep",
        "custom",
    }
)


@dataclass(frozen=True)
class Rule:
    action: str = "placeholder"
    threshold: float = 0.0
    width: int = 10
    shift_days: int = 0
    replacement: str = "[GENERALIZED]"
    custom: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.action, str)
            or self.action not in ACTIONS
            or type(self.threshold) not in {int, float}
            or not 0 <= self.threshold <= 1
        ):
            raise ValueError("Invalid transformation action or threshold")
        if type(self.width) is not int or self.width <= 0:
            raise ValueError("Bucket width must be a positive integer")
        if type(self.shift_days) is not int or abs(self.shift_days) > 36500:
            raise ValueError("Invalid date shift")
        if not isinstance(self.replacement, str) or len(self.replacement) > 1024:
            raise ValueError("Invalid replacement")
        if self.custom is not None and (not isinstance(self.custom, str) or not self.custom):
            raise ValueError("Custom transformation name must be a nonempty string")
        if self.action == "custom" and self.custom is None:
            raise ValueError("Custom transformation requires a registered name")


@dataclass(frozen=True)
class Policy:
    name: str = "strict"
    default: Rule = field(default_factory=Rule)
    entities: dict[str, Rule] = field(default_factory=dict)
    domains: dict[str, dict[str, Rule]] = field(default_factory=dict)
    require_ner: bool = True
    review_below: float = 0.75
    allow_residual_types: tuple[str, ...] = ()
    token_scope: str = "document"
    independent_check: str = "none"
    require_human_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or len(self.name) > 128:
            raise ValueError("Policy name must be a short nonempty string")
        if not isinstance(self.token_scope, str) or self.token_scope not in {
            "document",
            "dataset",
            "tenant",
            "session",
        }:
            raise ValueError("Invalid token scope")
        if (
            type(self.require_ner) is not bool
            or type(self.require_human_review) is not bool
            or type(self.review_below) not in {int, float}
            or not 0 <= self.review_below <= 1
        ):
            raise ValueError("Invalid release gate")
        if not isinstance(self.independent_check, str) or self.independent_check not in {
            "none",
            "proper_nouns",
        }:
            raise ValueError("Invalid independent output check")
        if not isinstance(self.default, Rule):
            raise ValueError("default must be a Rule")
        if not isinstance(self.entities, dict) or not all(
            isinstance(k, str) and k and isinstance(v, Rule) for k, v in self.entities.items()
        ):
            raise ValueError("entities must map to Rules")
        if not isinstance(self.domains, dict) or not all(
            isinstance(domain, str)
            and domain
            and isinstance(rules, dict)
            and all(isinstance(k, str) and k and isinstance(v, Rule) for k, v in rules.items())
            for domain, rules in self.domains.items()
        ):
            raise ValueError("domains must map entity categories to Rules")
        if not isinstance(self.allow_residual_types, (tuple, list)) or not all(
            isinstance(v, str) and v for v in self.allow_residual_types
        ):
            raise ValueError("allow_residual_types must be a list of category names")

    @classmethod
    def strict(cls, *, require_ner: bool = True) -> Policy:
        return cls(require_ner=require_ner)

    @classmethod
    def strict_pdf(cls, *, require_ner: bool = True) -> Policy:
        """Physical pixel removal for reconstructed PDFs, with explicit semantics."""
        return cls(name="strict_pdf", default=Rule("redact"), require_ner=require_ner)

    @classmethod
    def context(
        cls,
        *,
        require_ner: bool = True,
        keep_clinical: bool = True,
        verify_proper_nouns: bool = True,
    ) -> Policy:
        """Local context-preserving pseudonymization with Spanish placeholders.

        Identifiers become indexed, role-aware placeholders (``[PERSONA_1]``,
        ``[MEDICO_1]``, ``[LUGAR_1]``); ages are bucketed; sex/gender mentions are
        kept. With ``keep_clinical`` the clinical content itself (diagnoses,
        conditions, treatments, medications) is retained for analysis; set it to
        ``False`` to replace it too. Retained health information and relationships
        remain sensitive: pseudonymization does not establish anonymity.
        ``verify_proper_nouns`` adds a text-only review heuristic. Other formats
        require review instead of silently bypassing this check.
        """
        if any(
            type(value) is not bool for value in (require_ner, keep_clinical, verify_proper_nouns)
        ):
            raise ValueError("Context policy switches must be booleans")
        keep = Rule("keep")
        entities = {"DEMOGRAPHIC": keep, "AGE": Rule("bucket", width=10)}
        if keep_clinical:
            entities.update(
                {
                    kind: keep
                    for kind in (
                        "DIAGNOSIS",
                        "MEDICAL_CONDITION",
                        "TREATMENT",
                        "MEDICATION",
                        "CLINICAL_OBSERVATION",
                        "MEDICAL_HISTORY",
                        "MEDICAL_ATTRIBUTE",
                    )
                }
            )
        return cls(
            name="context",
            default=Rule("indexed"),
            entities=entities,
            require_ner=require_ner,
            token_scope="session",
            independent_check="proper_nouns" if verify_proper_nouns else "none",
            require_human_review=True,
        )

    @classmethod
    def llm(
        cls,
        *,
        require_ner: bool = True,
        keep_clinical: bool = True,
        verify_proper_nouns: bool = True,
    ) -> Policy:
        """Compatibility preset; no LLM is loaded or called.

        New applications should use :meth:`context`. The legacy name and policy
        fingerprint are preserved for existing callers and encrypted vaults.
        """
        return replace(
            cls.context(
                require_ner=require_ner,
                keep_clinical=keep_clinical,
                verify_proper_nouns=verify_proper_nouns,
            ),
            name="llm",
            require_human_review=False,
        )

    def rule(self, entity_type: str, domain: str | None = None) -> Rule:
        if domain and entity_type in self.domains.get(domain, {}):
            return self.domains[domain][entity_type]
        return self.entities.get(entity_type, self.default)

    def fingerprint(self) -> str:
        configuration = asdict(self)
        # Preserve fingerprints for pre-0.6 policies that had no human-review
        # setting. Supervised policies carry the new setting in their identity.
        if not self.require_human_review:
            configuration.pop("require_human_review")
        return hashlib.sha256(
            json.dumps(
                configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()
        ).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Policy:
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError("Unknown policy configuration key or invalid root")
        data = dict(value)
        try:
            if "default" in data:
                data["default"] = Rule(**data["default"])
            data["entities"] = {k: Rule(**v) for k, v in data.get("entities", {}).items()}
            data["domains"] = {
                d: {k: Rule(**v) for k, v in rules.items()}
                for d, rules in data.get("domains", {}).items()
            }
            residual = data.get("allow_residual_types", ())
            if not isinstance(residual, (tuple, list)):
                raise ValueError("allow_residual_types must be a list")
            data["allow_residual_types"] = tuple(residual)
            return cls(**data)
        except (TypeError, AttributeError, ValueError):
            raise ValueError("Invalid policy configuration") from None

    @classmethod
    def from_yaml(cls, path: str | Path) -> Policy:
        try:
            import yaml
        except ImportError:
            raise ImportError("Install deidflow[yaml] to load YAML policies") from None
        try:
            with Path(path).open(encoding="utf-8") as handle:
                value = yaml.safe_load(handle)
        except (OSError, yaml.YAMLError):
            raise ValueError("Cannot read policy configuration") from None
        return cls.from_dict(value)
