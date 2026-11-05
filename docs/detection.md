# Detection and source fidelity

`RuleDetector` is a reusable, compiled Spanish-language recognizer (Mexican core rules plus
the international pack in [COUNTRIES.md](COUNTRIES.md)). It detects
email, phone patterns, RFC, CURP, CLABE, Luhn-compatible payment cards, explicit
person/address/identifier labels, credentials, dates, ages, and a small medical
lexicon **only with nearby patient/clinical context**. It does not provide a
complete Spanish name, address, credential, health or regional-ID inventory.
The extensible taxonomy lists categories independently of their implementation:
an enum member does not imply a recognizer is available for it.

Findings never store the matched value. Their offsets are half-open Python
Unicode character offsets into the exact source fragment, before normalization.
`SourceLocation` links the fragment to a page, cell, row, part, JSON path or
bounding box when the reader supplies it. Normalization is restricted to
identifier validation, not document offsets. Line-wrapped RFC/CURP remain linked
to their original span. OCR confusables are deliberately not silently corrected:
`O` is not automatically changed to `0`. Unrecognized degradation remains a
recall limitation and requires assurance review.

## Evidence is not confirmation

`ValidationResult` distinguishes pattern compatibility, structural validity and
checksum validity. `confirmed` is always false: no registry, bank or identity
service is queried. Date/state checks do not establish issuance or ownership.
Identifier-shaped candidates with invalid checksums remain findings with lower
raw scores; a mistyped identifier may still be sensitive. These raw scores are
ranking signals, not calibrated probabilities (`confidence=None`).

CLABE weights are 3,7,1 and the complement of the weighted sum modulo ten.
See [Banco de México Circular 12/2018, Annex 4](https://sidof.segob.gob.mx/notas/docFuente/5537421).
CURP structure follows the [SEGOB assignment instructions](https://sidof.segob.gob.mx/notas/docFuente/5526717);
the local implementation additionally uses the conventional weighted CURP
check-digit algorithm, tested against fixed examples. RFC structure is described
in [SAT's financial-account reporting guidance](https://sat.gob.mx/cs/Satellite?blobcol=urldata&blobkey=id&blobtable=MungoBlobs&blobwhere=1461174992692&ssbinary=true).
The local modulo-eleven check is not an SAT registry check; generic invoice RFCs
are explicit exceptions. Current official issuance rules and additional sex/state
code extensions need review before regulated deployment.

Explicitly labelled CURP/RFC/CLABE also produce uncertain candidates when OCR
substitutions break the normal structure. The original characters remain intact
in the finding span; the validator returns `invalid` and confidence stays unset.

## Fusion, extension and models

`fuse()` combines only identical category/location/span candidates, retains
detector provenance, keeps the strongest evidence rank, and never averages
incompatible scores. Overlapping entities remain in scan results. For transforms,
`non_overlapping()` unions their covered spans; policy selection must occur first.
User-defined `RegexRecognizer` supports named capture groups and validation hooks.
These are trusted code: applications must review their runtime and ReDoS behavior.

`SpacyNER` loads only a user-specified local model directory, lazily. CPU is the
default, CUDA is explicit and requires an independently provisioned compatible
spaCy/CuPy installation. An unavailable model or inference failure raises an
explicit error. No model is downloaded and no fallback reduces protection. A
shared adapter serializes pipeline inference. `detect_batch()` streams bounded
overlapping windows through `nlp.pipe`; offsets are reconstructed and duplicate
complete entities deduplicated. Boundary fragments are retained when no complete
entity supersedes them. Entities longer than the overlap and contextual model
errors remain limitations. Default spaCy labels map PER/PERSON to PERSON and
LOC/GPE to LOCATION; organizations are not presumed confidential. Customers may
provide their own label mapping and licensed local model.

The evaluated development-only baseline was `es_core_news_sm` 3.8.0, whose
[official model release](https://github.com/explosion/spacy-models/releases/tag/es_core_news_sm-3.8.0)
declares **GNU GPL 3.0** for its weights (the spaCy library itself is MIT).
Weights are kept outside this repository and distribution. The official wheel's
SHA-256, verified on download, is
`e451a83d6df79b87e9eed0cb553f03e99e36a3bab18a7b79f0dcfd1fdf875e12`.
This baseline choice is not a recommendation to redistribute GPL weights inside
a proprietary product; select and review a commercially compatible local model
or separately resolve its licensing before distribution.

Deterministic rules operate without spaCy. Enabling a statistical model changes
the detection coverage and must be evaluated on held-out domain data. Neither
mode proves absence of all sensitive content.

`deidflow.detectors.resolution.resolve_exact_mentions` groups exact normalized,
typed mentions with a scope-separated HMAC identifier. It keeps no plaintext
mapping and does not fuzzy-merge people. Single-word names remain separate;
aliases require explicit application-provided mappings. Equal full names are
matching mentions, not proof of one person's identity.

## Public clinical validation

The v0.3 contextual additions cover explicit Spanish clinical identifier/person
fields, real calendar dates and patient-associated demographics. They retain
prior protected candidates, including invalid-checksum evidence. A necessary
condition prefilter avoids scanning all added patterns on text that cannot match
any of them; every finding and its metadata are identical with/without this
prefilter on 500 MEDDOCAN dev/test documents and synthetic property tests. It
changes runtime, not recognition rules. The aggregate equivalence hashes are in
`benchmarks/results/public-trigger-equivalence.json`.

[Detection quality](DETECTION_QUALITY.md) reports independent gold recall,
remaining type/boundary gaps and English TAB failure. Heuristic scores are not
calibrated and no public ECE is measured. Hard negatives protect known parsing
boundaries; they do not estimate specificity on arbitrary real documents. The
numeric-only age boundary is retained for existing bucketing semantics even
where a wider gold phrase creates an exact-span mismatch.
