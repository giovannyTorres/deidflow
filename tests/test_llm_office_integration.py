from __future__ import annotations

import re
import zipfile

import pytest
from test_office_xlsx import make_xlsx

from deidflow import DeidEngine, Policy


@pytest.mark.parametrize("schema_fast_path", [False, True])
@pytest.mark.parametrize("independent_check", [False, True])
def test_xlsx_llm_tokens_share_allocator_and_require_review(
    tmp_path, schema_fast_path, independent_check
):
    source = make_xlsx(tmp_path / "source.xlsx")
    engine = DeidEngine(country="ES", schema_fast_path=schema_fast_path)
    result = engine.deidentify(
        source,
        output=tmp_path / "candidate.xlsx",
        policy=Policy.llm(require_ner=False, verify_proper_nouns=independent_check),
    )
    assert result.status == "REVIEW_REQUIRED", result.issues
    assert not result.release_approved and result.output_path is not None
    assert "RESIDUAL_FINDINGS" not in result.issues
    with zipfile.ZipFile(result.output_path) as archive:
        worksheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        text = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist())
    assert len(set(re.findall(r"\[PERSONA_\d+\]", worksheet))) >= 2
    for sensitive in ("María López García", "Pedro Ruiz Soto", "12345678Z", "87654321X"):
        assert sensitive not in text
    assert ("INDEPENDENT_CHECK_REQUIRES_REVIEW" in result.issues) is independent_check
