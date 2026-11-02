# Local Spanish OCR

The installed validation runtime is **Tesseract 5.5.4**, compiled locally from
the pinned upstream release commit `7e548e6eff172f38f97664afe7f7ce40db36c8d6`.
The final runtime lives outside the repository:

```text
../../work/tesseract-5.5.4/bin/tesseract.exe
../../work/tesseract-5.5.4/share/tessdata/
```

No public repository, document upload, PATH change, registry modification or
installer execution was required. An earlier distribution was used only as an
installation probe; final tests and benchmarks select the patched source build.
Model/binary assets are not included in Python wheels or source distributions.

## Why a source build

The Windows package-manager manifest lagged behind upstream's patched release.
Tesseract 5.5.4 includes upstream security fixes, so the final implementation does
not depend on that older package. Existing UCRT GCC/G++ 16.2.0, Ninja and CMake
built the engine using pinned official MSYS2 UCRT libraries, including Leptonica
1.87.0, libpng 1.6.59, libtiff 4.7.2 and OpenJPEG 2.5.4.

`docs/ocr-build-lock.json` records all 21 dependency-package versions, source
URLs, SHA-256 digests and declared licenses. `docs/ocr-assets.json` records the
actual compiled executable/DLL digests and build flags. The pinned source
archive is checked by SHA-256; GitHub's API reported the upstream release tag's
PGP signature valid, but that signature was not independently verified locally.
MSYS2 archive hashes were checked against the official HTTPS repository's
database metadata. These checks establish the selected source/integrity chain,
not proof of absence of native-library vulnerabilities.

The final build disables CURL, libarchive, ScrollView graphics, the legacy OCR
engine, training tools and OpenMP. LSTM inference and runtime-selected CPU SIMD
remain enabled. Images reach Tesseract as PNG; no URL input is accepted by the
adapter. The language assets are official `tessdata_fast` Spanish and English
from pinned commit `87416418657359cb625c412a48b6e1d6d41c29bd`.

## API

```python
from pathlib import Path
from deidflow import DeidEngine
from deidflow.ocr import TesseractOCR

assets = Path("../../work/tesseract-5.5.4").resolve()
ocr = TesseractOCR(
    executable=str(assets / "bin/tesseract.exe"),
    tessdata_dir=assets / "share/tessdata",
    language="spa+eng",
    psm=3,  # Automatic page layout; 6 suits a single uniform text block.
    oem=1,  # Local LSTM models; this build has no legacy engine.
    threads=1,
    timeout=60,
    min_confidence=50,
)
engine = DeidEngine(ocr=ocr)
graph = engine.read("scanned.pdf")
if not graph.complete:
    raise RuntimeError("Extraction needs review")
```

OCR uses a direct, shell-free argument vector. PNG input and UTF-8 TSV output
travel through subprocess pipes, without sensitive temporary images or OCR text
files. Each call receives its own executable, data directory, segmentation mode
and thread environment; it does not mutate process-global pytesseract settings.
The per-call `OMP_THREAD_LIMIT` bounds compatible alternate builds, while the
delivered source build has OpenMP disabled. Calls can run independently in
bounded application worker pools. The adapter starts a local process per image;
model initialization cost is included in the measured page latency.

Timeouts, missing binaries/languages, malformed TSV, invalid geometry, NaN scores
and empty OCR results fail explicitly with sanitized `OCRError`. Recognized
low-confidence words remain in output; they are not silently filtered out.
Their engine confidence is not calibrated entity confidence. Reader/redaction
release gates decide whether low-confidence regions require review.
Native Tesseract may exit successfully after one requested language fails to load;
the adapter inspects failure diagnostics and blocks that fallback. The delivered
engine also silently substitutes PSM 11 for PSM 12, so PSM 12 is explicitly
unsupported. TSV generation is configured directly, without relying on an
external `configs/tsv` file in a customer's model directory.

## Reproduce the installed runtime

Run from the repository root. This is an **explicit development-time download and
build**, separate from fully local inference:

```powershell
python scripts/install_local_ocr.py `
  --destination ../../work/tesseract-5.5.4 `
  --work-dir ../../work `
  --bsdtar 'C:\Users\Giovanny\anaconda3\Library\bin\bsdtar.exe' `
  --workers 8
```

Prerequisites: UCRT GCC/G++ 16.2-compatible toolchain, CMake, Ninja, bsdtar with
zstd support, and the development environment's `certifi` CA bundle. Compiler and
build-tool executables must be on the build process's PATH. The script downloads
only pinned assets, checks hashes, refuses a modified preexisting source tree,
builds and copies local DLLs/models/notices, and writes the private asset manifest.
It does not select a newer version or silently replace a conflicting local DLL.
MSYS2 may eventually prune these exact archives; preserve the verified private
download cache or perform a separately reviewed lock update.

To run the real integration tests, set:

```powershell
$env:DEIDFLOW_TEST_TESSERACT = (Resolve-Path ../../work/tesseract-5.5.4/bin/tesseract.exe)
$env:DEIDFLOW_TEST_TESSDATA_DIR = (Resolve-Path ../../work/tesseract-5.5.4/share/tessdata)
python -m pytest -q tests/test_ocr_local.py
```

Tests include actual Spanish accents, a planted email, socket-denied Python
inference, concurrent independent calls, missing language data, timeouts,
sanitized failures, strict settings and malformed TSV. Page-level CER/WER,
entity recall and throughput are recorded by `scripts/benchmark_pdf_ocr.py`;
see the separate benchmark methodology and results.

## Licensing and security limits

Tesseract source and the selected `tessdata_fast` models are Apache-2.0. Native
libraries have separate BSD, LGPL, GPL-with-runtime-exception and other terms;
their original notices are retained under the private runtime's `share/licenses`.
GCC runtime exceptions and binary redistribution obligations require review.
No license grant for native assets is implied by DeidFlow's package license.
`pip-audit` covers Python distributions, **not** this native dependency graph.
Use current native security advisories and OS process/resource isolation for
hostile documents; patched upstream source does not establish complete security.

Primary sources: [upstream 5.5.4 release](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.4),
[official language assets](https://github.com/tesseract-ocr/tessdata_fast),
[MSYS2 UCRT repository](https://repo.msys2.org/mingw/ucrt64/), and
[Tesseract installation documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html).
