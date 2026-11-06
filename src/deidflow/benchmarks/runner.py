"""Measured CPU benchmarks.  Optional baselines never silently fall back."""

from __future__ import annotations

import gc
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from .datasets import Example, synthetic_corpus, write_corpus
from .metrics import evaluate


@contextmanager
def offline_network() -> Iterator[dict[str, int]]:
    """Deny DNS/connect calls; even swallowed network attempts fail the run."""
    state = {"attempts": 0}

    def deny(*args: Any, **kwargs: Any) -> Any:
        state["attempts"] += 1
        raise RuntimeError("Network access is disabled for benchmark inference")

    with (
        patch("socket.getaddrinfo", side_effect=deny),
        patch("socket.create_connection", side_effect=deny),
        patch("socket.socket.connect", deny),
        patch("socket.socket.connect_ex", deny),
    ):
        yield state
    if state["attempts"]:
        raise RuntimeError("Benchmark attempted network access; results must not be accepted")


def machine_metadata() -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "versions": {},
        "execution": "CPU",
        "gpu_memory_bytes": None,
    }
    for name in (
        "deidflow",
        "psutil",
        "spacy",
        "presidio-analyzer",
        "DataProfiler",
        "numpy",
        "scikit-learn",
    ):
        try:
            metadata["versions"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            metadata["versions"][name] = None
    try:
        import psutil

        metadata["physical_memory_bytes"] = psutil.virtual_memory().total
        metadata["physical_cpu_count"] = psutil.cpu_count(logical=False)
    except ImportError:
        metadata["physical_memory_bytes"] = None
    return metadata


def measure(
    call: Callable[[], Any], *, units: int = 1, size_bytes: int = 0
) -> tuple[dict[str, Any], Any]:
    """Sample process-tree RSS every 10ms, including already resident models.

    Peak is sampled and can miss shorter allocations. CPU percentage is on the
    single-core scale (100%=one fully used core), not a machine-normalized rate.
    """
    done = threading.Event()
    peak_rss = 0
    peak_tree_rss = 0
    cpu_before = cpu_after = None
    try:
        import psutil

        process = psutil.Process()
        cpu_before = sum(process.cpu_times()[:2])

        def sample() -> None:
            nonlocal peak_rss, peak_tree_rss
            while not done.is_set():
                try:
                    own = process.memory_info().rss
                    tree = own
                    for child in process.children(recursive=True):
                        try:
                            tree += child.memory_info().rss
                        except psutil.Error:
                            pass
                    peak_rss = max(peak_rss, own)
                    peak_tree_rss = max(peak_tree_rss, tree)
                except psutil.Error:
                    pass
                done.wait(0.01)

        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
    except ImportError:
        process = monitor = None
    started = time.perf_counter()
    try:
        result = call()
    finally:
        elapsed = time.perf_counter() - started
        done.set()
        if monitor is not None:
            monitor.join(timeout=1)
            cpu_after = sum(process.cpu_times()[:2])
    return {
        "elapsed_seconds": elapsed,
        "units": units,
        "records_per_second": units / elapsed,
        "mb_per_second": size_bytes / 1_000_000 / elapsed if size_bytes else None,
        "peak_rss_bytes": peak_rss or None,
        "peak_process_tree_rss_bytes": peak_tree_rss or None,
        "cpu_percent_one_core_scale": ((cpu_after - cpu_before) / elapsed * 100)
        if cpu_before is not None and cpu_after is not None and elapsed >= 0.1
        else None,
        "cpu_accounting_note": "Unavailable for runs below 100ms due to OS CPU-time granularity"
        if elapsed < 0.1
        else "Process CPU only; excludes child CPU",
    }, result


def _percentile(values: Sequence[float], fraction: float) -> float:
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def benchmark_detector(
    name: str,
    detect: Callable[[str], Sequence[Any]],
    examples: Sequence[Example],
    *,
    repeats: int = 3,
) -> dict[str, Any]:
    if repeats < 1 or not examples:
        raise ValueError("Benchmarks require examples and at least one repeat")
    warm_start = time.perf_counter()
    detect(examples[0].text)
    warm_latency = time.perf_counter() - warm_start
    size_bytes = sum(len(example.text.encode("utf-8")) for example in examples)
    runs = []
    predictions: list[Sequence[Any]] = []
    latencies: list[float] = []
    for _ in range(repeats):
        gc.collect()

        def run() -> list[Sequence[Any]]:
            outputs = []
            for example in examples:
                start = time.perf_counter()
                outputs.append(detect(example.text))
                latencies.append(time.perf_counter() - start)
            return outputs

        measurement, predictions = measure(run, units=len(examples), size_bytes=size_bytes)
        runs.append(measurement)
    return {
        "name": name,
        "status": "measured",
        "documents": len(examples),
        "bytes": size_bytes,
        "warmup_documents": 1,
        "repeats": repeats,
        "first_call_seconds": warm_latency,
        "p50_latency_seconds": statistics.median(latencies),
        "p95_latency_seconds": _percentile(latencies, 0.95),
        "median_records_per_second": statistics.median(run["records_per_second"] for run in runs),
        "runs": runs,
        "exact": evaluate(examples, predictions).to_dict(),
        "overlap": evaluate(examples, predictions, exact=False).to_dict(),
        "person_only_exact": evaluate(
            [
                replace(
                    example,
                    spans=tuple(span for span in example.spans if span.entity_type == "PERSON"),
                )
                for example in examples
            ],
            [
                [finding for finding in findings if finding.entity_type == "PERSON"]
                for findings in predictions
            ],
        ).to_dict(),
        "prediction_sha256": __import__("hashlib")
        .sha256(
            json.dumps(
                [
                    [(str(f.entity_type), f.start, f.end) for f in findings]
                    for findings in predictions
                ]
            ).encode()
        )
        .hexdigest(),
    }


def _spacy_baseline(path: str | Path) -> Callable[[str], Sequence[Any]]:
    if not Path(path).is_dir():
        raise ValueError("Spanish baseline requires an existing local spaCy model directory")
    import spacy

    from deidflow.core import Finding

    model = spacy.load(path)
    if model.lang != "es" or "ner" not in model.pipe_names:
        raise ValueError("Baseline model must contain Spanish NER")
    mapping = {
        "PER": "PERSON",
        "PERSON": "PERSON",
        "LOC": "LOCATION",
        "GPE": "LOCATION",
        "LOCATION": "LOCATION",
        "ORG": "ORGANIZATION",
    }

    def detect(text: str) -> list[Any]:
        return [
            Finding(
                mapping[e.label_],
                e.start_char,
                e.end_char,
                0.5,
                "baseline.spacy",
                model_version=str(model.meta.get("version", "unknown")),
            )
            for e in model(text).ents
            if e.label_ in mapping
        ]

    return detect


def _presidio_baseline(path: str | Path) -> Callable[[str], Sequence[Any]]:
    if not Path(path).is_dir():
        raise ValueError("Presidio requires an existing local Spanish spaCy model")
    import tldextract
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import SpacyNlpEngine

    from deidflow.core import Finding

    nlp = SpacyNlpEngine(models=[{"lang_code": "es", "model_name": str(Path(path).resolve())}])
    nlp.load()
    analyzer = AnalyzerEngine(nlp_engine=nlp, supported_languages=["es"])
    # Presidio EmailRecognizer calls tldextract.extract. Use its installed
    # bundled suffix snapshot explicitly; default extract may fetch a PSL.
    offline_suffix_extractor = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
    mapping = {
        "PERSON": "PERSON",
        "LOCATION": "LOCATION",
        "EMAIL_ADDRESS": "EMAIL",
        "PHONE_NUMBER": "PHONE",
        "CREDIT_CARD": "PAYMENT_CARD",
        "DATE_TIME": "DATE",
        "ES_NIF": "NATIONAL_ID",
        "ES_NIE": "NATIONAL_ID",
        "IBAN_CODE": "BANK_ACCOUNT",
        "ORGANIZATION": "ORGANIZATION",
        "IP_ADDRESS": "IP_ADDRESS",
        "US_SSN": "NATIONAL_ID",
        "NRP": "DEMOGRAPHIC",
    }

    def detect(text: str) -> list[Any]:
        with patch("tldextract.extract", offline_suffix_extractor):
            results = analyzer.analyze(text=text, language="es", score_threshold=0.0)
        return [
            Finding(
                mapping.get(f.entity_type, f.entity_type),
                f.start,
                f.end,
                f.score,
                "baseline.presidio",
            )
            for f in results
        ]

    return detect


def _run_detection_benchmarks(
    output: str | Path,
    *,
    count: int = 150,
    repeats: int = 3,
    seed: int = 1729,
    spacy_model: str | Path | None = None,
) -> dict[str, Any]:
    from deidflow import DeidEngine
    from deidflow.detectors import RuleDetector

    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for split in ("train", "validation", "test"):
        corpus = synthetic_corpus(split, count=count, seed=seed)
        hashes[split] = write_corpus(target / f"{split}.jsonl", corpus)
    examples = synthetic_corpus("test", count=count, seed=seed)
    deterministic = RuleDetector(contextual=False)
    hybrid = DeidEngine()
    baselines = [
        benchmark_detector("deterministic_only", deterministic.detect, examples, repeats=repeats),
        benchmark_detector(
            "deidflow_contextual_rules", hybrid.scan_text, examples, repeats=repeats
        ),
    ]
    if spacy_model is not None:
        for name, factory in (
            ("spacy_spanish", _spacy_baseline),
            ("presidio_spanish", _presidio_baseline),
        ):
            factory_started = time.perf_counter()
            try:
                detect = factory(spacy_model)
            except (ImportError, ValueError, OSError):
                baselines.append(
                    {
                        "name": name,
                        "status": "unavailable",
                        "reason": "installed compatible baseline and local Spanish model required",
                    }
                )
            else:
                initialization = time.perf_counter() - factory_started
                baseline = benchmark_detector(name, detect, examples, repeats=repeats)
                baseline["factory_initialization_seconds"] = initialization
                baselines.append(baseline)
        from deidflow.nlp import SpacyNER

        model = SpacyNER(spacy_model)
        statistical_hybrid = DeidEngine(nlp=model)
        baselines.append(
            benchmark_detector(
                "deidflow_rules_plus_local_spacy",
                statistical_hybrid.scan_text,
                examples,
                repeats=repeats,
            )
        )
        token_count = sum(len(model._load().make_doc(example.text)) for example in examples)
        for baseline in baselines:
            if baseline["status"] == "measured" and baseline["name"] in {
                "spacy_spanish",
                "presidio_spanish",
                "deidflow_rules_plus_local_spacy",
                "deidflow_rules_plus_local_spacy_batch",
            }:
                baseline["nlp_token_count"] = token_count
                baseline["nlp_tokens_per_second"] = token_count / statistics.median(
                    run["elapsed_seconds"] for run in baseline["runs"]
                )
        batched, batch_predictions = measure(
            lambda: statistical_hybrid.scan_texts([e.text for e in examples]),
            units=len(examples),
            size_bytes=sum(len(e.text.encode("utf-8")) for e in examples),
        )
        baselines.append(
            {
                "name": "deidflow_rules_plus_local_spacy_batch",
                "status": "measured",
                "documents": len(examples),
                "repeats": 1,
                "batch_size": model.batch_size,
                "runs": [batched],
                "nlp_token_count": token_count,
                "nlp_tokens_per_second": token_count / batched["elapsed_seconds"],
                "exact": evaluate(examples, batch_predictions).to_dict(),
                "note": "One batch timing; compare to single-item only as exploratory, not established speedup",
            }
        )
    else:
        baselines.extend(
            {
                "name": name,
                "status": "unavailable",
                "reason": "No local Spanish NER model supplied; no model download attempted",
            }
            for name in ("spacy_spanish", "presidio_spanish")
        )
    baselines.append(
        {
            "name": "dataprofiler",
            "status": "unavailable",
            "reason": "DataProfiler and a reviewed local labeler are not installed. Structured/character-level labeler comparison remains an explicit benchmark backlog item. No model was fetched.",
        }
    )
    cold_code = (
        "from deidflow import DeidEngine; DeidEngine().scan_text('correo: persona@example.org')"
    )
    cold_started = time.perf_counter()
    cold = subprocess.run(
        [sys.executable, "-c", cold_code], capture_output=True, timeout=60, check=False
    )
    cold_seconds = time.perf_counter() - cold_started
    result = {
        "schema_version": 1,
        "seed": seed,
        "dataset_sha256": hashes,
        "dataset_scope": "Synthetic Spanish/Mexican challenge corpus; templates and value namespaces are split-disjoint; not an enterprise accuracy estimate",
        "machine": machine_metadata(),
        "baselines": baselines,
        "cold_start_subprocess_seconds": cold_seconds if cold.returncode == 0 else None,
        "model_assets": {
            "spanish_model": Path(spacy_model).name if spacy_model else None,
            "bundled": False,
            "weight_license": "User-supplied; recorded separately in licensing report",
        },
        "measurement_notes": [
            "Cold start includes Python interpreter and import",
            "CPU scale is one core; RSS sampled every 10 ms and includes resident imports/models; baselines share the interpreter, so resident RSS is not an isolated per-model memory comparison",
            "Exact matching is type+start+end; overlap matching requires same type and any intersecting span",
            "False-redaction rate is covered non-gold characters / all non-gold characters",
            "ECE is unavailable unless predictions provide calibrated confidence",
            "Deterministic-only excludes contextual rules; contextual rules have no statistical NER; rules_plus_local_spacy is the statistical hybrid",
            "Not all taxonomy categories appear in this small corpus; no aggregate superiority claim",
        ],
    }
    (target / "detection.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def run_detection_benchmarks(
    output: str | Path,
    *,
    count: int = 150,
    repeats: int = 3,
    seed: int = 1729,
    spacy_model: str | Path | None = None,
) -> dict[str, Any]:
    with offline_network() as state:
        result = _run_detection_benchmarks(
            output, count=count, repeats=repeats, seed=seed, spacy_model=spacy_model
        )
        result["network_guard"] = {
            "socket_connect_and_dns": "denied",
            "attempted_connections": state["attempts"],
            "presidio_suffix_list": "installed tldextract bundled snapshot, remote suffix URLs disabled",
        }
        (Path(output) / "detection.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return result
