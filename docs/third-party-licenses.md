# Third-party licensing and naming inventory

The base package has **zero runtime dependencies** and is not publicly released.
`LICENSE` reserves the copyright holder's licensing decisions. No public
repository, remote push or PyPI publication was performed. This inventory
documents components; it does not provide trademark or legal clearance.

| Component | Use | Declared upstream terms / review boundary |
| --- | --- | --- |
| Python | Runtime | PSF terms; local Python 3.11.9 |
| spaCy | Optional discriminative adapter | MIT code; model licenses are separate |
| es_core_news_sm 3.8.0 | Private benchmark asset only | **GPL-3.0 model**, not bundled or selected by default |
| pypdf | Optional native PDF extraction | BSD-3-Clause; no PyMuPDF dependency |
| pypdfium2 / PDFium | Optional rasterization | Apache-2.0/BSD-3-Clause wrapper; PDFium/Bundled third-party notices separately |
| Pillow 13.0.0 | Optional image processing | MIT-CMU and bundled codec notices; see installed package licenses |
| Tesseract 5.5.4 / tessdata_fast spa+eng | Explicit local OCR | Apache-2.0; source-built runtime, DLL and model hashes/notices separately inventoried; no wrapper dependency |
| pandas / NumPy / SciPy / scikit-learn | Optional tables and CPU learner | BSD-family code; binary wheels bundle additional native libraries/notices |
| Polars | Optional DataFrame adapter | MIT; native runtime distribution separately inventoried |
| PyArrow | Optional Parquet | Apache-2.0 with bundled component notices |
| PyYAML | Optional policies | MIT |
| Joblib | Optional local model storage | BSD-3-Clause; only trusted private assets |
| Presidio Analyzer | Optional external evaluation | MIT code; local NLP asset terms remain separate |
| psutil / ReportLab | Benchmark measurement and generated PDFs | BSD-family terms |
| pytest / Hypothesis / Ruff / Mypy / Hatchling | Development/validation | Respect individual MIT/BSD/Apache terms in local inventory |

`license-inventory.json` captures names, exact versions, declared license
expressions, classifiers, complete metadata license text where available, and
installed license-file paths for the whole validation environment. This includes
transitive and native distributions rather than asserting that a top-level
license settles all redistribution obligations. Preserve the applicable license
texts/notices if shipping a binary or vendored environment. `requirements-lock-windows-py311.txt`
records the exact final tested environment, not a universal cross-platform lock.

The v0.2 local OCR build additionally records all pinned native package versions,
URLs, SHA-256 and license declarations in `ocr-build-lock.json`; `ocr-assets.json`
records actual compiled binaries and model hashes. Original native notices are
kept in the private runtime outside the repository. This includes LGPL libraries
and GCC runtime exceptions, whose redistribution obligations need separate review.
No native executable/DLL/traineddata is in Python wheels or source archives.
See [local OCR setup](local-ocr.md) for upstream patch level and limitations.
`pytesseract` remains in the historical validation environment inventory but is no
longer an OCR extra dependency or runtime adapter import.

The downloaded Spanish model is stored outside this repository in the parent
workspace `work/models`, solely to execute real local baselines. Official wheel
SHA-256: `e451a83d6df79b87e9eed0cb553f03e99e36a3bab18a7b79f0dcfd1fdf875e12`.
It is not in the wheel, source archive or repository. A commercial deployment
must select model weights with independently acceptable terms; changing from a
GPL-licensed model is not accomplished merely by using an MIT adapter.

Primary references:

- [Official Spanish model release and license](https://github.com/explosion/spacy-models/releases/tag/es_core_news_sm-3.8.0)
- [Official Spanish model metadata](https://raw.githubusercontent.com/explosion/spacy-models/master/meta/es_core_news_sm-3.8.0.json)
- [spaCy model and language documentation](https://spacy.io/usage/models)
- [pypdf distribution license metadata](https://pypi.org/project/pypdf/)
- [PDFium license information](https://pypdfium2.readthedocs.io/en/stable/readme.html#licensing)
- [Pillow distribution metadata](https://pypi.org/project/pillow/13.0.0/)
- [Tesseract repository and license](https://github.com/tesseract-ocr/tesseract)
- [Presidio repository](https://github.com/microsoft/presidio)

Development inspection on 2026-11-02 found PyPI's `deidflow` project JSON endpoint
returning HTTP 404 and GitHub repository search returning zero matching
repositories. General web searches did not establish an exact product conflict.
These observations do not reserve a name, establish trademark rights, or prove
package-name availability at publication time. Recheck registries and legal
conflicts before any authorized publication. Similar `deid` projects exist.
