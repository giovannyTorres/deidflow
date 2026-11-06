"""Conservative, detector-independent inspection of textual output and maps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deidflow.transformations import SourceMap

from ._package_io import MAX_RECORDS, MAX_RESOURCE_BYTES


@dataclass(frozen=True)
class TextRequirement:
    start: int
    end: int
    action: str
    operators: tuple[str, ...]
    release_states: tuple[str, ...]
    entity_type: str
    ranges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class TransformationOutput:
    text: str | None
    mappings: tuple[SourceMap, ...]
    release_status: str = "APPROVED"


def resolve_requirements(
    rows: list[dict[str, Any]], mentions: dict[str, dict[str, Any]], precedence: list[str]
) -> tuple[list[TextRequirement], int]:
    """Apply declared precedence by elementary interval, keeping each target."""
    targets = []
    for row in rows:
        target = mentions[row["mention_id"]] if row["mention_id"] else row
        targets.append((row, target))
    endpoints = sorted({target[key] for _, target in targets for key in ("start", "end")})
    ranges: dict[str, list[tuple[int, int]]] = {row["expectation_id"]: [] for row in rows}
    overridden = 0
    for start, end in zip(endpoints, endpoints[1:], strict=False):
        active = [
            (row, target) for row, target in targets if target["start"] <= start < target["end"]
        ]
        actions = {row["action"] for row, _ in active}
        if not actions:
            continue
        chosen = min(actions, key=precedence.index) if len(actions) > 1 else next(iter(actions))
        if len(actions) > 1:
            overridden += end - start
        for row, _target in active:
            if row["action"] == chosen:
                ranges[row["expectation_id"]].append((start, end))
    return [
        TextRequirement(
            target["start"],
            target["end"],
            row["action"],
            tuple(row["allowed_operators"]),
            tuple(row["acceptable_release_states"]),
            target.get("entity_type", "REGION"),
            tuple(ranges[row["expectation_id"]]),
        )
        for row, target in targets
    ], overridden


def _validated_source_maps(text: str, output: TransformationOutput) -> tuple[SourceMap, ...] | None:
    if (
        not isinstance(output, TransformationOutput)
        or not isinstance(output.text, str)
        or len(output.text) > MAX_RESOURCE_BYTES
        or output.release_status not in {"APPROVED", "REVIEW_REQUIRED", "BLOCKED", "UNSUPPORTED"}
        or not isinstance(output.mappings, (tuple, list))
        or len(output.mappings) > MAX_RECORDS
    ):
        return None
    source_cursor = output_cursor = 0
    copied = []
    for item in output.mappings:
        if not isinstance(item, SourceMap):
            return None
        source_start, source_end, output_start, output_end = (
            item.source_start,
            item.source_end,
            item.output_start,
            item.output_end,
        )
        if (
            any(
                type(value) is not int
                for value in (source_start, source_end, output_start, output_end)
            )
            or not source_cursor <= source_start < source_end <= len(text)
            or not output_cursor <= output_start <= output_end <= len(output.text)
            or text[source_cursor:source_start] != output.text[output_cursor:output_start]
            or not isinstance(item.action, str)
            or not isinstance(item.entity_types, tuple)
            or not item.entity_types
            or any(not isinstance(label, str) for label in item.entity_types)
        ):
            return None
        copied.append(
            SourceMap(
                source_start,
                source_end,
                output_start,
                output_end,
                tuple(item.entity_types),
                item.action,
            )
        )
        source_cursor, output_cursor = source_end, output_end
    if text[source_cursor:] != output.text[output_cursor:]:
        return None
    return tuple(copied)


def _removal_verified(text: str, emitted: str, mapping: SourceMap) -> bool:
    original = text[mapping.source_start : mapping.source_end]
    replacement = emitted[mapping.output_start : mapping.output_end]
    if original == replacement:
        return False
    if mapping.action == "suppress":
        return replacement == ""
    if mapping.action == "redact":
        return replacement == "█" * len(original)
    if mapping.action == "placeholder":
        return replacement in {f"[{label}]" for label in mapping.entity_types}
    # Keyed/indexed/custom/generalizing operators require their own verifier.
    return False


def inspect_text_output(
    text: str, requirements: list[TextRequirement], output: TransformationOutput | None
) -> dict[str, Any]:
    mappings = _validated_source_maps(text, output) if output is not None else None
    valid_maps = mappings is not None
    preserved = bytearray(b"\x01") * len(text) if valid_maps else bytearray(len(text))
    removed = bytearray(len(text))
    operators: list[tuple[int, int, str]] = []
    if mappings is not None and output is not None and output.text is not None:
        for mapping in mappings:
            source_start, source_end, output_start, output_end = (
                mapping.source_start,
                mapping.source_end,
                mapping.output_start,
                mapping.output_end,
            )
            original, replacement = (
                text[source_start:source_end],
                output.text[output_start:output_end],
            )
            preserved[source_start:source_end] = (
                bytes(left == right for left, right in zip(original, replacement, strict=True))
                if len(original) == len(replacement)
                else bytes(source_end - source_start)
            )
            if _removal_verified(text, output.text, mapping):
                removed[source_start:source_end] = b"\x01" * (source_end - source_start)
            operators.append((source_start, source_end, mapping.action))
    preserve_required = bytearray(b"\x01") * len(text)
    for requirement in requirements:
        if requirement.action != "preserve":
            for start, end in requirement.ranges:
                preserve_required[start:end] = bytes(end - start)
    counts = dict.fromkeys(
        (
            "required_removals",
            "removed_mentions",
            "leaked_mentions",
            "unverifiable_mentions",
            "required_context_spans",
            "preserved_context_spans",
            "review_required_spans",
            "unverifiable_spans",
            "failed_requirements",
            "excluded_requirements",
        ),
        0,
    )
    for requirement in requirements:
        positions = [
            position for start, end in requirement.ranges for position in range(start, end)
        ]
        if not positions:
            counts["excluded_requirements"] += 1
            continue
        action = requirement.action
        if action == "remove":
            counts["required_removals"] += 1
            allowed = all(
                operator in requirement.operators
                for a, b, operator in operators
                if any(a < end and start < b for start, end in requirement.ranges)
            )
            original = text[requirement.start : requirement.end]
            literal_survives = (
                output is not None and isinstance(output.text, str) and original in output.text
            )
            ambiguous_survival = literal_survives and text.count(original) > 1
            verified = (
                valid_maps
                and allowed
                and not ambiguous_survival
                and all(removed[position] for position in positions)
            )
            # A unique literal can be attributed even with invalid maps. A
            # surviving homonym without coordinates remains uncertain.
            leaked = (
                output is not None
                and output.text is not None
                and (
                    output.text == text
                    or (literal_survives and not ambiguous_survival)
                    or (
                        valid_maps
                        and any(
                            preserved[position] and not removed[position] for position in positions
                        )
                    )
                )
            )
            counts["removed_mentions"] += int(verified and not leaked)
            counts["leaked_mentions"] += int(leaked)
            counts["unverifiable_mentions"] += int(not verified and not leaked)
            counts["failed_requirements"] += int(not verified or leaked)
        elif action == "preserve":
            counts["required_context_spans"] += 1
            intact = valid_maps and all(preserved[position] for position in positions)
            counts["preserved_context_spans"] += int(intact)
            counts["failed_requirements"] += int(not intact)
        elif action == "review_required":
            counts["review_required_spans"] += 1
            counts["failed_requirements"] += 1
        else:
            counts["unverifiable_spans"] += 1
            counts["failed_requirements"] += 1
        if output is not None and output.release_status not in requirement.release_states:
            counts["failed_requirements"] += 1
    required = sum(preserve_required)
    retained = sum(
        bool(keep and present) for keep, present in zip(preserve_required, preserved, strict=True)
    )
    joint = valid_maps and counts["failed_requirements"] == 0 and retained == required
    return {
        **counts,
        "retention_required_chars": required,
        "retained_chars": retained,
        "overtransformed_chars": required - retained if valid_maps else 0,
        "unverified_preservation_chars": required if not valid_maps else 0,
        "verification_complete": valid_maps
        and not counts["unverifiable_spans"]
        and not counts["unverifiable_mentions"],
        "joint_success": bool(joint and output is not None),
        "output_observable": output is not None and output.text is not None,
    }
