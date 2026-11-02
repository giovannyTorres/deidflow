"""Export local package license metadata. This is inventory, not legal clearance."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

inventory = []
for distribution in importlib.metadata.distributions():
    metadata = distribution.metadata
    inventory.append(
        {
            "name": metadata["Name"],
            "version": distribution.version,
            "license_expression": metadata.get("License-Expression"),
            "license_metadata": metadata.get("License"),
            "classifiers": [
                c for c in metadata.get_all("Classifier", []) if c.startswith("License")
            ],
            "license_files": [
                str(p)
                for p in distribution.files or []
                if "license" in str(p).lower() or "copying" in str(p).lower()
            ],
        }
    )
destination = Path("docs/license-inventory.json")
destination.parent.mkdir(exist_ok=True)
destination.write_text(
    json.dumps(sorted(inventory, key=lambda x: x["name"].lower()), indent=2), encoding="utf-8"
)
print(f"Inventoried {len(inventory)} installed distributions")
