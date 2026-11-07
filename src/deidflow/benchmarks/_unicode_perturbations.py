"""Version-one identifier-only Unicode edit contracts, separate from inference."""

from __future__ import annotations

from typing import Any

UNICODE_RECIPES = ("format_chars.v1", "fullwidth.v1")
FORMAT_CHARS = "\u00ad\u200b\u200d\u2060\ufeff"
IDENTIFIER_TYPES = frozenset(
    {"PERSON", "ADDRESS", "RFC", "CURP", "CLABE", "PAYMENT_CARD", "EMAIL", "PHONE"}
)


def unicode_parts(
    text: str,
    recipe: str,
    mentions: list[dict[str, Any]],
    boundaries: set[int],
    seed: int,
) -> tuple[list[str], dict[str, Any]]:
    selected = bytearray(len(text))
    for mention in mentions:
        if mention["entity_type"] in IDENTIFIER_TYPES:
            selected[mention["start"] : mention["end"]] = b"\x01" * (
                mention["end"] - mention["start"]
            )
    parts = list(text)
    changed = 0
    for index, character in enumerate(text):
        if selected[index] and recipe == "fullwidth.v1" and "!" <= character <= "~":
            parts[index] = chr(ord(character) + 0xFEE0)
            changed += 1
        if (
            recipe == "format_chars.v1"
            and index + 1 < len(text)
            and selected[index]
            and selected[index + 1]
            and index + 1 not in boundaries
            and character.isalnum()
            and text[index + 1].isalnum()
        ):
            parts[index] += FORMAT_CHARS[(seed + index + 1) % len(FORMAT_CHARS)]
            changed += 1
    return parts, {
        "selection": "direct_identifier_mentions.v1",
        "algorithm": "seed_plus_boundary_mod5.v1"
        if recipe == "format_chars.v1"
        else "ascii_graphics_to_fullwidth.v1",
        "changed_codepoints": changed,
    }
