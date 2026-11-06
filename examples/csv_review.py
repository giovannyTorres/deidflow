"""Exercise the CSV CLI with fully annotated fictional financial cells.

This demonstration accepts only an output directory. Its complete source and
human decisions are authored below; it cannot approve arbitrary user input.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from dataclasses import asdict
from pathlib import Path

from deidflow.cli import main as cli
from deidflow.csv_review import CSVReviewPlan
from deidflow.private.security import protect
from deidflow.review import ReviewDecision


def run(destination: Path) -> dict[str, object]:
    destination.mkdir(mode=0o700)
    protect(destination, directory=True)
    cells = [
        ["cliente", "correo", "concepto", "importe"],
        ["Ana López", "ana@example.test", "pago de renta, noviembre", "1250.50"],
        ["Ana López", "ana@example.test", "referencia privada ZQX-771\npago puntual", "80.00"],
    ]
    gold: dict[tuple[int, int], list[tuple[int, int, str]]] = {}
    for row in (1, 2):
        gold[row, 0] = [(0, len(cells[row][0]), "PERSON")]
        gold[row, 1] = [(0, len(cells[row][1]), "EMAIL")]
    start = cells[2][2].index("ZQX-771")
    gold[2, 2] = [(start, start + len("ZQX-771"), "CUSTOMER_ID")]
    source = destination / "fictional.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\r\n").writerows(cells)

    signing = destination / "review.key"
    assert cli(["keygen", str(signing)]) == 0
    plan_path = destination / "plan.json"
    base = [str(source), "--format", "csv", "--pack", "financial"]
    assert cli(["review", "plan", *base, "--output", str(plan_path)]) == 0
    plan = CSVReviewPlan.from_json(plan_path.read_text(encoding="utf-8"))
    decisions = []
    additions = 0
    for cell in plan.cells:
        coordinate = (cell.row, cell.column)
        wanted = gold.get(coordinate, [])
        confirmed = set()
        for span in cell.review.spans:
            interval = (span.start, span.end, span.entity_type)
            # The final reference is deliberately supplied as an explicit human
            # interval, even if a model proposes an overlapping interpretation.
            if interval in wanted and coordinate != (2, 2):
                decision = ReviewDecision.confirm(span.span_id)
                confirmed.add(interval)
            else:
                overlap = any(span.start < end and start < span.end for start, end, _ in wanted)
                decision = ReviewDecision.reject(
                    span.span_id, reason="span_correction" if overlap else "not_personal"
                )
            decisions.append({"row": cell.row, "column": cell.column, "decision": asdict(decision)})
        for start, end, kind in wanted:
            if (start, end, kind) not in confirmed:
                additions += 1
                decisions.append(
                    {
                        "row": cell.row,
                        "column": cell.column,
                        "decision": asdict(ReviewDecision.add(start, end, kind)),
                    }
                )
    decision_path = destination / "decisions.json"
    decision_path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    apply_args = [
        "review",
        "apply",
        *base,
        "--plan",
        str(plan_path),
        "--decisions",
        str(decision_path),
        "--reviewer-id",
        "reviewer-0123456789abcdef",
        "--signing-key-file",
        str(signing),
    ]
    preview = destination / "candidate"
    assert cli([*apply_args, "--output", str(preview)]) == 2
    assert (preview / "candidate.csv").is_file()
    assert not (preview / "approved.csv").exists()

    approved = destination / "approved"
    assert cli([*apply_args, "--output", str(approved), "--approve", "--source-complete"]) == 0
    output = approved / "approved.csv"
    assert output.is_file() and not (approved / "candidate.csv").exists()
    sanitized = list(csv.reader(io.StringIO(output.read_bytes().decode("utf-8"), newline="")))
    assert len(sanitized) == len(cells) and all(len(row) == 4 for row in sanitized)
    assert sanitized[0] == cells[0]
    assert sanitized[1][0] == sanitized[2][0] != cells[1][0]
    assert sanitized[1][1] == sanitized[2][1] != cells[1][1]
    assert sanitized[1][2] == cells[1][2]
    assert sanitized[1][3] == cells[1][3] and sanitized[2][3] == cells[2][3]
    assert "ZQX-771" not in sanitized[2][2]
    assert sanitized[2][2].startswith("referencia privada ")
    assert sanitized[2][2].endswith("\npago puntual")
    assert additions >= 1

    verify_args = [
        "review",
        "verify",
        *base,
        "--receipt",
        str(approved / "receipt.json"),
        "--signing-key-file",
        str(signing),
    ]
    assert cli([*verify_args, "--output", str(output)]) == 0
    tampered = destination / "tampered.csv"
    tampered.write_bytes(output.read_bytes() + b"\r\n")
    assert cli([*verify_args, "--output", str(tampered)]) == 2

    summary: dict[str, object] = {
        "evidence": "authored_synthetic_demonstration",
        "data_rows": 2,
        "columns": 4,
        "manual_additions": additions,
        "repeated_identity_consistent": True,
        "amounts_preserved": True,
        "preview_requires_review": True,
        "signed_output_verified": True,
        "tampering_rejected": True,
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for the fictional demo"
    )
    print(json.dumps(run(parser.parse_args().output)))
