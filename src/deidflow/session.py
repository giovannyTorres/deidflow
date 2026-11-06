"""Local de-identification sessions, explicit relations and encrypted resumption.

No model service or network operation is performed. Graphs expose issued tokens,
not original values. Exact text equality is linkage evidence, not proof that two
mentions refer to one real-world person; relationships are explicitly declared.
"""

from __future__ import annotations

import base64
import copy
import hmac
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deidflow.core import EntityType
from deidflow.engine import DeidEngine, ReleaseStatus, Result
from deidflow.placeholders import (
    PLACEHOLDER,
    ROLE_LABELS_ES,
    PlaceholderAllocator,
    canonical_placeholder,
)
from deidflow.policies import Policy
from deidflow.vault import (
    EncryptedVault,
    MemoryVault,
    Vault,
    _finite_number,
    _invalid_constant,
    _unique_pairs,
)

if TYPE_CHECKING:
    from deidflow.review import ReviewDecision, ReviewedText, ReviewPlan

_FORMAT = "deidflow.session.v1"
_MAX_BYTES = 64 * 1024 * 1024
_MAX_RECORDS = 100000
_MAX_EVIDENCE = 128
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_RELATIONS = frozenset(
    {
        "familiar_de",
        "atiende_a",
        "pertenece_a",
        "representa_a",
        "parte_de",
        "titular_de",
        "contraparte_de",
        "relacionado_con",
    }
)


class _ExpiredSession(ValueError):
    pass


def _aead(key: bytes) -> Any:
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("Session encryption requires a 32-byte key")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise ImportError("Install deidflow[vault] for encrypted sessions") from None
    return AESGCM(key)


def _opaque(value: Any, prefix: str) -> bool:
    return isinstance(value, str) and re.fullmatch(prefix + r"_[0-9a-f]{32}", value) is not None


@dataclass(frozen=True)
class ReidentifyResult:
    text: str = field(repr=False)
    restored: int
    unknown: tuple[str, ...]


class DeidSession:
    """One local identity scope, with optional reversible storage and encrypted snapshots.

    Processing and saves are serialized. Source text is never stored in the public
    graph; graph identifiers and relationships remain potentially sensitive metadata.
    """

    def __init__(
        self,
        engine: DeidEngine,
        *,
        policy: Policy | None = None,
        vault: Vault | None = None,
        reversible: bool = True,
        allocator: PlaceholderAllocator | None = None,
        clock: Callable[[], float] | None = None,
        model_digest: str | None = None,
    ) -> None:
        self.engine = engine
        self.policy = policy or Policy.context()
        self._policy_fingerprint = self.policy.fingerprint()
        self._engine_model_digest = getattr(engine, "model_digest", None)
        self._model_digest: str | None = (
            model_digest if model_digest is not None else self._engine_model_digest
        )
        if (
            self._engine_model_digest is not None
            and self._engine_model_digest != self._model_digest
        ):
            raise ValueError("Session model digest conflicts with its engine")
        if self._model_digest is not None and (
            not isinstance(self._model_digest, str) or not _HASH.fullmatch(self._model_digest)
        ):
            raise ValueError("Model digest must be a SHA-256 identifier")
        if type(reversible) is not bool:
            raise ValueError("reversible must be a boolean")
        self.reversible = reversible
        if not reversible and vault is not None:
            raise ValueError("An irreversible session cannot use a vault")
        self.vault: Vault | None = (
            (vault if vault is not None else MemoryVault(clock=clock or time.time))
            if reversible
            else None
        )
        self.allocator = (
            allocator if allocator is not None else PlaceholderAllocator(compatible_context=True)
        )
        self.session_id = getattr(self.vault, "session_id", secrets.token_hex(16))
        if not isinstance(self.session_id, str) or not _IDENTIFIER.fullmatch(self.session_id):
            raise ValueError("Session requires an opaque identity")
        self._clock: Callable[[], float] = (
            clock if clock is not None else getattr(self.vault, "_clock", time.time)
        )
        if not callable(self._clock):
            raise ValueError("Session clock must be callable")
        self._created_at = _finite_number(self._clock())
        self._expires_at: float | None = getattr(self.vault, "_expires", None)
        self._documents: list[dict[str, Any]] = []
        self._occurrences: list[dict[str, Any]] = []
        self._relations: list[dict[str, Any]] = []
        self._closed = False
        self._lock = threading.RLock()
        if self.vault is not None:
            stored = {token: self.vault.get(token) for token in self.vault.placeholders()}
            self.allocator.bind_vault(self.session_id, stored)

    def __enter__(self) -> DeidSession:
        self._active()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _active(self) -> None:
        if self._closed:
            raise ValueError("Session closed")
        now = _finite_number(self._clock())
        expires = self._expires_at
        if isinstance(self.vault, MemoryVault) and self.vault._expires is not None:
            expires = (
                min(expires, self.vault._expires) if expires is not None else self.vault._expires
            )
        if expires is not None and now >= expires:
            self.close()
            raise _ExpiredSession("Session expired")
        if self.policy.fingerprint() != self._policy_fingerprint:
            raise ValueError("Session policy changed; start a separate session")
        if getattr(self.engine, "model_digest", None) != self._engine_model_digest:
            raise ValueError("Session model configuration changed")

    def _restore_allocator(self, state: dict[str, Any]) -> None:
        restored = PlaceholderAllocator._from_state(state)
        # Preserve an explicitly supplied allocator object's identity.
        vars(self.allocator).clear()
        vars(self.allocator).update(vars(restored))

    def deidentify(self, text: str, *, domain: str | None = None) -> Result:
        return self._process(
            text,
            lambda: self.engine.deidentify_text(
                text,
                policy=self.policy,
                document_id=self.session_id,
                domain=domain,
                placeholders=self.allocator,
            ),
        )

    def apply_review(
        self,
        text: str,
        plan: ReviewPlan,
        decisions: list[ReviewDecision] | tuple[ReviewDecision, ...],
        *,
        reviewer_id: str,
        approve: bool = False,
        source_complete: bool = False,
        signing_key: bytes | None = None,
        domain: str | None = None,
    ) -> ReviewedText:
        """Apply a source-bound human review through this session's identity scope.

        The review module enforces complete decisions, fresh model/policy bindings,
        residual checks and explicit human approval. The session records all indexed
        corrections in the same vault and occurrence graph as ordinary processing.
        """
        from deidflow.review import apply_review

        digest = self._model_digest
        if digest is None:
            raise ValueError("Session review requires an explicit model digest")
        reviewed: ReviewedText | None = None

        def transform() -> Result:
            nonlocal reviewed
            reviewed = apply_review(
                self.engine,
                text,
                plan,
                decisions,
                policy=self.policy,
                model_digest=digest,
                reviewer_id=reviewer_id,
                approve=approve,
                source_complete=source_complete,
                signing_key=signing_key,
                domain=domain,
                placeholders=self.allocator,
            )
            return reviewed.result

        self._process(text, transform)
        assert reviewed is not None
        return reviewed

    def _process(self, text: str, transform: Callable[[], Result]) -> Result:
        with self._lock:
            self._active()
            if len(self._documents) >= _MAX_RECORDS:
                raise ValueError("Session document limit exceeded")
            before = self.allocator._dump_state()
            try:
                self.allocator.reserve_source(text)
                result = transform()
                self._active()
                if result.status in {ReleaseStatus.BLOCKED, ReleaseStatus.UNSUPPORTED}:
                    self._restore_allocator(before)
                    return result
                pending = []
                issued = self.allocator.issued()
                identities = {token: identity for identity, token in self.allocator._exact.items()}
                for mapping in result.mappings:
                    if mapping.action != "indexed":
                        continue
                    token = (result.output_text or "")[mapping.output_start : mapping.output_end]
                    if (
                        token not in issued
                        or not 0 <= mapping.source_start < mapping.source_end <= len(text)
                        or not 0
                        <= mapping.output_start
                        < mapping.output_end
                        <= len(result.output_text or "")
                    ):
                        raise ValueError("Invalid session transformation receipt")
                    value = text[mapping.source_start : mapping.source_end]
                    identity = identities.get(token)
                    if identity is None or not hmac.compare_digest(
                        identity[3], self.allocator._hash(unicodedata.normalize("NFC", value))
                    ):
                        raise ValueError("Invalid session transformation identity")
                    if self.vault is not None:
                        previous = self.vault.get(token)
                        if previous is not None and unicodedata.normalize(
                            "NFC", previous
                        ) != unicodedata.normalize("NFC", value):
                            raise ValueError("Vault conflicts with issued placeholder")
                    pending.append(
                        (
                            token,
                            value,
                            mapping.source_start,
                            mapping.source_end,
                            mapping.output_start,
                            mapping.output_end,
                        )
                    )
                if len(self._occurrences) + len(pending) > _MAX_RECORDS:
                    raise ValueError("Session occurrence limit exceeded")
                old_tokens = {item["token"] for item in before["identities"]}
                if not set(issued) - old_tokens <= {item[0] for item in pending}:
                    raise ValueError("Incomplete session transformation receipt")
                if self.vault is not None:
                    values = {token: self.vault.get(token) for token in self.vault.placeholders()}
                    for token, value, _, _, _, _ in pending:
                        values.setdefault(token, value)
                    self._active()
                    self.allocator.bind_vault(self.session_id, values)
                self._active()
            except Exception:
                if not self._closed:
                    self._restore_allocator(before)
                raise
            # Store only after all receipts and bounds have been validated. A failing
            # external/expired vault closes the session rather than leaving partial state.
            try:
                if self.vault is not None:
                    for token, value, _, _, _, _ in pending:
                        if self.vault.get(token) is None:
                            self.vault.put(token, value)
                self._active()
            except Exception:
                self.close()
                raise ValueError("Session storage failed; session closed") from None
            document_id = "doc_" + secrets.token_hex(16)
            occurrences = [
                {
                    "id": "occ_" + secrets.token_hex(16),
                    "entity_id": token,
                    "document_id": document_id,
                    "start": start,
                    "end": end,
                    "output_start": output_start,
                    "output_end": output_end,
                }
                for token, _, start, end, output_start, output_end in pending
            ]
            self._documents.append(
                {
                    "id": document_id,
                    "status": str(result.status),
                    "sequence": len(self._documents) + 1,
                }
            )
            self._occurrences.extend(occurrences)
            result.audit.update(
                {
                    "session_id": self.session_id,
                    "document_id": document_id,
                    "occurrence_ids": [item["id"] for item in occurrences],
                }
            )
            return result

    def reidentify(self, text: str, *, strict: bool = True) -> ReidentifyResult:
        with self._lock:
            if type(strict) is not bool:
                raise ValueError("strict must be a boolean")
            try:
                self._active()
            except _ExpiredSession:
                if strict:
                    raise
                unknown_tokens = tuple(
                    dict.fromkeys(
                        canonical_placeholder(
                            match.group("label") or match.group("bare_label"),
                            match.group("index") or match.group("bare_index"),
                        )
                        for match in PLACEHOLDER.finditer(text)
                    )
                )
                return ReidentifyResult(text, 0, unknown_tokens)
            if self.vault is None:
                raise ValueError("This session is irreversible; no vault was kept")
            vault = self.vault
            issued = self.allocator.issued()
            identities = {token: identity for identity, token in self.allocator._exact.items()}
            restored = 0
            unknown: list[str] = []

            def replace(match: Any) -> str:
                nonlocal restored
                token = canonical_placeholder(
                    match.group("label") or match.group("bare_label"),
                    match.group("index") or match.group("bare_index"),
                )
                value = vault.get(token) if token in issued else None
                if value is None:
                    unknown.append(token)
                    return str(match.group(0))
                identity = identities.get(token)
                if identity is None or not hmac.compare_digest(
                    identity[3], self.allocator._hash(unicodedata.normalize("NFC", value))
                ):
                    raise ValueError("Vault conflicts with issued placeholder")
                restored += 1
                return value

            output = PLACEHOLDER.sub(replace, text)
            self._active()
            if strict and unknown:
                raise ValueError("Response contains placeholders not issued by this session")
            return ReidentifyResult(output, restored, tuple(dict.fromkeys(unknown)))

    def placeholders(self) -> dict[str, tuple[str, str | None]]:
        """Issued token metadata, retained for compatibility; never original values."""
        with self._lock:
            if self._closed:
                return {}
            try:
                self._active()
            except _ExpiredSession:
                return {}
            return self.allocator.issued()

    def graph(self) -> dict[str, Any]:
        """Return independent, value-free graph metadata; no source text or vault keys."""
        with self._lock:
            self._active()
            known_types = {item.value for item in EntityType} | {"AMOUNT"}
            genders = {
                token: context[1] for token, context in self.allocator.context_metadata().items()
            }
            entities = [
                {
                    "id": token,
                    "type": kind if kind in known_types else "OTHER_SENSITIVE",
                    "role": role if role in ROLE_LABELS_ES else None,
                    "gender": genders.get(token) if genders.get(token) in {"f", "m"} else None,
                }
                for token, (kind, role) in self.allocator.issued().items()
            ]
            return copy.deepcopy(
                {
                    "schema_version": 1,
                    "session_id": self.session_id,
                    "entities": entities,
                    "documents": self._documents,
                    "occurrences": self._occurrences,
                    "relations": self._relations,
                }
            )

    def relate(
        self,
        source: str,
        relation: str,
        target: str,
        *,
        evidence_ids: Sequence[str],
        provenance: str = "human",
    ) -> dict[str, Any]:
        """Record an explicitly reviewed relation; never infer aliases or merge nodes."""
        with self._lock:
            self._active()
            issued = self.allocator.issued()
            if (
                not isinstance(source, str)
                or not isinstance(target, str)
                or source not in issued
                or target not in issued
                or source == target
            ):
                raise ValueError("Relationships require two distinct issued entity tokens")
            if not isinstance(relation, str) or relation not in _RELATIONS or provenance != "human":
                raise ValueError("Unknown relationship or provenance; human evidence required")
            if (
                not isinstance(evidence_ids, (list, tuple))
                or not 1 <= len(evidence_ids) <= _MAX_EVIDENCE
                or any(not isinstance(item, str) for item in evidence_ids)
                or len(set(evidence_ids)) != len(evidence_ids)
            ):
                raise ValueError("Invalid relationship evidence")
            occurrences = {item["id"]: item for item in self._occurrences}
            if any(item not in occurrences for item in evidence_ids):
                raise ValueError("Relationship evidence must refer to session occurrences")
            observed = {occurrences[item]["entity_id"] for item in evidence_ids}
            if not {source, target} <= observed:
                raise ValueError("Evidence must include an occurrence of both endpoints")
            record = {
                "source": source,
                "target": target,
                "relation": relation,
                "evidence_ids": list(evidence_ids),
                "provenance": provenance,
            }
            for existing in self._relations:
                if all(existing[key] == value for key, value in record.items()):
                    return copy.deepcopy(existing)
            if len(self._relations) >= _MAX_RECORDS:
                raise ValueError("Session relationship limit exceeded")
            record["id"] = "rel_" + secrets.token_hex(16)
            self._relations.append(record)
            return copy.deepcopy(record)

    def save(self, path: str | Path, *, key: bytes, ttl_seconds: float | None = None) -> None:
        """Create a new authenticated encrypted snapshot; never overwrite a file.

        The snapshot contains allocator state and, in reversible mode, original
        values. Store the 32-byte key separately. A new TTL may shorten existing
        expiry but cannot extend it. No engine/model object is serialized.
        """
        with self._lock:
            self._active()
            cipher = _aead(key)
            expires = self._expires_at
            if ttl_seconds is not None:
                seconds = _finite_number(ttl_seconds)
                if seconds <= 0:
                    raise ValueError("Session TTL must be positive")
                requested = _finite_number(_finite_number(self._clock()) + seconds)
                expires = min(expires, requested) if expires is not None else requested
            if self.vault is not None and not isinstance(self.vault, MemoryVault):
                raise ValueError("Session persistence requires a built-in vault")
            if isinstance(self.vault, MemoryVault) and self.vault._expires is not None:
                expires = (
                    min(expires, self.vault._expires)
                    if expires is not None
                    else self.vault._expires
                )
            values: dict[str, str] = {}
            if self.vault is not None:
                for token in self.vault.placeholders():
                    value = self.vault.get(token)
                    if not isinstance(value, str) or not value:
                        raise ValueError("Session vault is unavailable or expired")
                    value.encode("utf-8")
                    values[token] = value
                self.allocator.bind_vault(self.session_id, values)
            state = {
                "format": _FORMAT,
                "version": 1,
                "session_id": self.session_id,
                "created_at": self._created_at,
                "expires_at": expires,
                "reversible": self.reversible,
                "policy": asdict(self.policy),
                "policy_sha256": self._policy_fingerprint,
                "model_digest": self._model_digest,
                "allocator": self.allocator._dump_state(),
                "values": values,
                "documents": self._documents,
                "occurrences": self._occurrences,
                "relations": self._relations,
            }
            self._active()
            payload = json.dumps(
                state, ensure_ascii=True, allow_nan=False, separators=(",", ":")
            ).encode()
            if len(payload) > _MAX_BYTES:
                raise ValueError("Session snapshot exceeds size limit")
            nonce = secrets.token_bytes(12)
            ciphertext = nonce + cipher.encrypt(nonce, payload, _FORMAT.encode())
            envelope = json.dumps(
                {"format": _FORMAT, "ciphertext": base64.b64encode(ciphertext).decode("ascii")},
                separators=(",", ":"),
            ).encode()
            if len(envelope) > _MAX_BYTES:
                raise ValueError("Session snapshot exceeds size limit")
            target = Path(path)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    from deidflow.private.security import protect

                    protect(target, directory=False)
                    handle.write(envelope)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            self._expires_at = expires

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        key: bytes,
        engine: DeidEngine,
        policy: Policy | None = None,
        model_digest: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> DeidSession:
        """Authenticate and restore the whole session with a trusted caller-supplied engine.

        The stored policy is restored unless an identical policy is supplied.
        A saved model digest requires the same caller/engine digest. Snapshots
        never deserialize code, models, regex adapters or custom transformations.
        """
        cipher = _aead(key)
        session: DeidSession | None = None
        try:
            with Path(path).open("rb") as handle:
                raw = handle.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                raise ValueError
            envelope = json.loads(
                raw, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
            )
            if (
                not isinstance(envelope, dict)
                or set(envelope) != {"format", "ciphertext"}
                or envelope["format"] != _FORMAT
                or not isinstance(envelope["ciphertext"], str)
            ):
                raise ValueError
            encrypted = base64.b64decode(envelope["ciphertext"], validate=True)
            payload = cipher.decrypt(encrypted[:12], encrypted[12:], _FORMAT.encode())
            state = json.loads(
                payload, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
            )
            expected = {
                "format",
                "version",
                "session_id",
                "created_at",
                "expires_at",
                "reversible",
                "policy",
                "policy_sha256",
                "model_digest",
                "allocator",
                "values",
                "documents",
                "occurrences",
                "relations",
            }
            if not isinstance(state, dict) or set(state) != expected:
                raise ValueError
            if (
                state["format"] != _FORMAT
                or type(state["version"]) is not int
                or state["version"] != 1
            ):
                raise ValueError
            identifier = state["session_id"]
            if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier):
                raise ValueError
            created = _finite_number(state["created_at"])
            expires = None if state["expires_at"] is None else _finite_number(state["expires_at"])
            if expires is not None and (expires <= created or _finite_number(clock()) >= expires):
                raise ValueError
            if type(state["reversible"]) is not bool:
                raise ValueError
            stored_policy = Policy.from_dict(state["policy"])
            if (
                not isinstance(state["policy_sha256"], str)
                or not _HASH.fullmatch(state["policy_sha256"])
                or stored_policy.fingerprint() != state["policy_sha256"]
                or policy is not None
                and policy.fingerprint() != state["policy_sha256"]
            ):
                raise ValueError
            selected_model = (
                model_digest if model_digest is not None else getattr(engine, "model_digest", None)
            )
            if state["model_digest"] is not None and (
                not isinstance(state["model_digest"], str)
                or not _HASH.fullmatch(state["model_digest"])
            ):
                raise ValueError
            if selected_model != state["model_digest"]:
                raise ValueError
            allocator = PlaceholderAllocator._from_state(state["allocator"])
            if allocator._vault_session_id != (identifier if state["reversible"] else None):
                raise ValueError
            values = state["values"]
            if (
                not isinstance(values, dict)
                or len(values) > _MAX_RECORDS
                or any(
                    not isinstance(k, str) or not isinstance(v, str) or not v
                    for k, v in values.items()
                )
                or not state["reversible"]
                and values
            ):
                raise ValueError
            vault = None
            if state["reversible"]:
                allocator.bind_vault(identifier, values)
                vault = EncryptedVault(key, clock=clock, session_id=identifier)
                vault._expires = expires
                for token, value in values.items():
                    vault.put(token, value)
            session = cls(
                engine,
                policy=policy or stored_policy,
                vault=vault,
                reversible=state["reversible"],
                allocator=allocator,
                clock=clock,
                model_digest=selected_model,
            )
            session.session_id = identifier
            session._created_at, session._expires_at = created, expires
            session._restore_graph(state)
            session._active()
            return session
        except Exception:
            if session is not None:
                session.close()
            raise ValueError(
                "Unreadable, expired, incompatible or unauthenticated session"
            ) from None

    def _restore_graph(self, state: dict[str, Any]) -> None:
        documents, occurrences, relations = (
            state[name] for name in ("documents", "occurrences", "relations")
        )
        if any(
            not isinstance(items, list) or len(items) > _MAX_RECORDS
            for items in (documents, occurrences, relations)
        ):
            raise ValueError("Invalid session graph")
        ids: set[str] = set()
        for index, item in enumerate(documents, 1):
            if (
                not isinstance(item, dict)
                or set(item) != {"id", "status", "sequence"}
                or not _opaque(item["id"], "doc")
                or item["id"] in ids
                or item["status"] not in {"APPROVED", "REVIEW_REQUIRED"}
                or type(item["sequence"]) is not int
                or item["sequence"] != index
            ):
                raise ValueError("Invalid session document")
            ids.add(item["id"])
        issued = self.allocator.issued()
        seen: set[str] = set()
        for item in occurrences:
            if (
                not isinstance(item, dict)
                or set(item)
                != {"id", "entity_id", "document_id", "start", "end", "output_start", "output_end"}
                or not _opaque(item["id"], "occ")
                or item["id"] in seen
                or item["entity_id"] not in issued
                or item["document_id"] not in ids
                or any(
                    type(item[k]) is not int for k in ("start", "end", "output_start", "output_end")
                )
                or not 0 <= item["start"] < item["end"] <= 1024**3
                or not 0 <= item["output_start"] < item["output_end"] <= 1024**3
                or item["output_end"] - item["output_start"] != len(item["entity_id"])
            ):
                raise ValueError("Invalid session occurrence")
            seen.add(item["id"])
        # Validate relations through the same public rules, restoring their stable IDs.
        self._documents, self._occurrences = copy.deepcopy(documents), copy.deepcopy(occurrences)
        relation_ids: set[str] = set()
        for item in relations:
            if (
                not isinstance(item, dict)
                or set(item) != {"id", "source", "target", "relation", "evidence_ids", "provenance"}
                or not _opaque(item["id"], "rel")
                or item["id"] in relation_ids
            ):
                raise ValueError("Invalid session relation")
            before = len(self._relations)
            self.relate(
                item["source"],
                item["relation"],
                item["target"],
                evidence_ids=item["evidence_ids"],
                provenance=item["provenance"],
            )
            if len(self._relations) != before + 1:
                raise ValueError("Duplicate session relation")
            self._relations[-1]["id"] = item["id"]
            relation_ids.add(item["id"])

    def close(self) -> None:
        with self._lock:
            try:
                if self.vault is not None:
                    self.vault.clear()
            finally:
                self.allocator.reset()
                self._documents.clear()
                self._occurrences.clear()
                self._relations.clear()
                self._closed = True


__all__ = ["DeidSession", "ReidentifyResult"]
