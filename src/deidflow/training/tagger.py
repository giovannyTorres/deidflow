"""Train the local span tagger (averaged structured perceptron) on annotated text.

Training needs NumPy (``deidflow[training]``); the resulting model runs without
it. Training is deterministic for a given corpus, configuration and seed, so a
model file can be rebuilt byte for byte.

Protocol: weights are fitted on ``train`` only. ``validation`` selects the epoch
(early stopping on exact span F1) and fits the Platt calibration. No test data
is accepted here; evaluate the returned model separately, once.
"""

from __future__ import annotations

import math
import random
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from deidflow.benchmarks.datasets import Example
from deidflow.nlp.tagger import (
    FEATURE_SET,
    FORMAT,
    FORMAT_VERSION,
    SpanTagger,
    allowed_transition,
    bio_tags,
    feature_key,
    token_features,
    tokenize,
)

_MASK = -1e9


def _require_numpy() -> Any:
    try:
        import numpy
    except ImportError:
        raise RuntimeError("Tagger training requires the training extra (NumPy)") from None
    return numpy


def _encode(
    np: Any,
    examples: Sequence[Example],
    tag_index: Mapping[str, int],
    feature_index: dict[str, int] | None,
    min_feature_docs: int,
) -> tuple[list[tuple[Any, Any, Any, list[tuple[int, int]]]], dict[str, int], dict[str, int]]:
    """Encode documents as CSR feature ids, gold tags and token offsets.

    When ``feature_index`` is ``None`` it is built from these examples, keeping
    only features that occur in at least ``min_feature_docs`` documents.
    """
    keyed = []
    unaligned = 0
    unknown_types = 0
    frequency: Counter[str] = Counter()
    for example in examples:
        tokens = tokenize(example.text)
        if not tokens:
            continue
        keys = [
            [feature_key(feature) for feature in features]
            for features in token_features(example.text, tokens)
        ]
        spans = []
        for span in example.spans:
            if "B-" + span.entity_type not in tag_index:
                unknown_types += 1
                continue
            spans.append((span.entity_type, span.start, span.end))
        tags, skipped = bio_tags(tokens, spans)
        unaligned += skipped
        keyed.append((keys, [tag_index[tag] for tag in tags], tokens))
        if feature_index is None:
            frequency.update({key for row in keys for key in row})
    if feature_index is None:
        feature_index = {}
        for key in sorted(k for k, n in frequency.items() if n >= min_feature_docs):
            feature_index[key] = len(feature_index)
    encoded = []
    for keys, gold, tokens in keyed:
        ids: list[int] = []
        offsets: list[int] = []
        for row in keys:
            offsets.append(len(ids))
            ids.extend(feature_index[key] for key in row if key in feature_index)
            if len(ids) == offsets[-1]:
                raise ValueError("Every token needs at least one known feature")
        encoded.append(
            (
                np.asarray(ids, dtype=np.int64),
                np.asarray(offsets, dtype=np.int64),
                np.asarray(gold, dtype=np.int64),
                tokens,
            )
        )
    return (
        encoded,
        feature_index,
        {"unaligned_spans": unaligned, "spans_of_unknown_type": unknown_types},
    )


def _viterbi(np: Any, emissions: Any, transitions: Any, start: Any) -> Any:
    count, size = emissions.shape
    back = np.zeros((count, size), dtype=np.int64)
    score = start + emissions[0]
    columns = np.arange(size)
    for t in range(1, count):
        candidates = score[:, None] + transitions
        back[t] = candidates.argmax(0)
        score = candidates[back[t], columns] + emissions[t]
    path = np.empty(count, dtype=np.int64)
    path[-1] = int(score.argmax())
    for t in range(count - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def _spans_from_path(
    tags: Sequence[str], path: Sequence[int], tokens: Sequence[tuple[int, int]]
) -> set[tuple[str, int, int]]:
    spans = set()
    index = 0
    while index < len(path):
        tag = tags[path[index]]
        if tag == "O":
            index += 1
            continue
        kind = tag[2:]
        stop = index + 1
        while stop < len(path) and tags[path[stop]] == "I-" + kind:
            stop += 1
        spans.add((kind, tokens[index][0], tokens[stop - 1][1]))
        index = stop
    return spans


def _f1(
    gold: Sequence[set[tuple[str, int, int]]], predicted: Sequence[set[Any]]
) -> dict[str, float]:
    tp = sum(len(g & p) for g, p in zip(gold, predicted, strict=True))
    fp = sum(len(p - g) for g, p in zip(gold, predicted, strict=True))
    fn = sum(len(g - p) for g, p in zip(gold, predicted, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _softplus(z: float) -> float:
    return z + math.log1p(math.exp(-z)) if z > 0 else math.log1p(math.exp(z))


def fit_platt(features: Sequence[float], outcomes: Sequence[int]) -> tuple[float, float]:
    """One-dimensional logistic regression (Platt 1999 smoothed targets).

    Damped Newton steps with backtracking on the negative log-likelihood, so a
    nearly separable calibration set cannot produce runaway coefficients.
    """
    if len(features) != len(outcomes) or not features:
        raise ValueError("Calibration needs paired, nonempty features and outcomes")
    positives = sum(outcomes)
    negatives = len(outcomes) - positives
    high = (positives + 1) / (positives + 2)
    low = 1 / (negatives + 2)
    targets = [high if y else low for y in outcomes]

    def loss(a: float, b: float) -> float:
        return sum(
            _softplus(a * x + b) - t * (a * x + b) for x, t in zip(features, targets, strict=True)
        )

    mean = sum(targets) / len(targets)
    a, b = 0.0, math.log(mean / (1 - mean))
    current = loss(a, b)
    for _ in range(200):
        g_a = g_b = h_aa = h_ab = h_bb = 0.0
        for x, t in zip(features, targets, strict=True):
            z = a * x + b
            p = 1 / (1 + math.exp(-z)) if z >= 0 else math.exp(z) / (1 + math.exp(z))
            g_a += (p - t) * x
            g_b += p - t
            w = p * (1 - p)
            h_aa += w * x * x
            h_ab += w * x
            h_bb += w
        h_aa += 1e-6
        h_bb += 1e-6
        determinant = h_aa * h_bb - h_ab * h_ab
        if determinant <= 0:
            break
        step_a = (h_bb * g_a - h_ab * g_b) / determinant
        step_b = (h_aa * g_b - h_ab * g_a) / determinant
        scale = 1.0
        while scale > 1e-8:
            candidate = loss(a - scale * step_a, b - scale * step_b)
            if candidate <= current:
                break
            scale /= 2
        else:
            break
        a, b = a - scale * step_a, b - scale * step_b
        improvement = current - candidate
        current = candidate
        if improvement < 1e-10:
            break
    return a, b


def train_span_tagger(
    train: Sequence[Example],
    validation: Sequence[Example],
    *,
    epochs: int = 20,
    patience: int = 4,
    seed: int = 1729,
    min_feature_docs: int = 2,
    prune_below: float = 0.0,
    entity_types: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(model, report)``. ``model`` is the JSON object for :class:`SpanTagger`."""
    if not train or not validation:
        raise ValueError("Training and validation examples are required")
    if any(example.split == "test" for example in (*train, *validation)):
        raise ValueError("Test examples must not be used for training or model selection")
    if epochs < 1 or patience < 1 or min_feature_docs < 1 or prune_below < 0:
        raise ValueError("Invalid tagger training configuration")
    np = _require_numpy()
    started = time.perf_counter()
    kinds = sorted(
        set(entity_types)
        if entity_types is not None
        else {span.entity_type for example in train for span in example.spans}
    )
    if not kinds:
        raise ValueError("Training examples contain no entity spans")
    tags = ["O"] + [prefix + kind for kind in kinds for prefix in ("B-", "I-")]
    tag_index = {tag: index for index, tag in enumerate(tags)}
    size = len(tags)
    train_docs, features, train_stats = _encode(np, train, tag_index, None, min_feature_docs)
    validation_docs, _, validation_stats = _encode(
        np, validation, tag_index, features, min_feature_docs
    )
    mask = np.array([[0.0 if allowed_transition(p, c) else _MASK for c in tags] for p in tags])
    start_mask = np.array([_MASK if tag.startswith("I-") else 0.0 for tag in tags])
    weights = np.zeros((len(features), size))
    weights_sum = np.zeros_like(weights)
    transitions = np.zeros((size, size))
    transitions_sum = np.zeros_like(transitions)
    start = np.zeros(size)
    start_sum = np.zeros_like(start)
    counter = 1
    rng = random.Random(seed)
    order = list(range(len(train_docs)))
    validation_gold = [
        {(s.entity_type, s.start, s.end) for s in example.spans if s.entity_type in kinds}
        for example in validation
        if tokenize(example.text)
    ]
    history = []
    best: dict[str, Any] | None = None
    stale = 0
    for epoch in range(1, epochs + 1):
        rng.shuffle(order)
        mistakes = 0
        for document in order:
            ids, offsets, gold, _ = train_docs[document]
            emissions = np.add.reduceat(weights[ids], offsets, axis=0)
            predicted = _viterbi(np, emissions, transitions + mask, start + start_mask)
            wrong = np.nonzero(predicted != gold)[0]
            if wrong.size:
                mistakes += 1
                lengths = np.diff(np.append(offsets, ids.size))
                for t in wrong:
                    row = ids[offsets[t] : offsets[t] + lengths[t]]
                    weights[row, gold[t]] += 1
                    weights[row, predicted[t]] -= 1
                    weights_sum[row, gold[t]] += counter
                    weights_sum[row, predicted[t]] -= counter
                for path, sign in ((gold, 1.0), (predicted, -1.0)):
                    np.add.at(transitions, (path[:-1], path[1:]), sign)
                    np.add.at(transitions_sum, (path[:-1], path[1:]), sign * counter)
                    start[path[0]] += sign
                    start_sum[path[0]] += sign * counter
            counter += 1
        averaged = weights - weights_sum / counter
        averaged_transitions = transitions - transitions_sum / counter
        averaged_start = start - start_sum / counter
        predictions = []
        for ids, offsets, _, tokens in validation_docs:
            emissions = np.add.reduceat(averaged[ids], offsets, axis=0)
            path = _viterbi(np, emissions, averaged_transitions + mask, averaged_start + start_mask)
            predictions.append(_spans_from_path(tags, path.tolist(), tokens))
        score = _f1(validation_gold, predictions)
        history.append({"epoch": epoch, "train_documents_with_errors": mistakes, **score})
        if log:
            log(
                f"epoch {epoch}: train docs with errors {mistakes}, "
                f"validation exact F1 {score['f1']:.4f}"
            )
        if best is None or score["f1"] > best["f1"]:
            best = {
                "epoch": epoch,
                "f1": score["f1"],
                "weights": averaged.copy(),
                "transitions": averaged_transitions.copy(),
                "start": averaged_start.copy(),
            }
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                break
    assert best is not None
    keys = sorted(features, key=features.__getitem__)
    stored: dict[str, list[list[float | int]]] = {}
    entries = 0
    for row, key in zip(best["weights"], keys, strict=True):
        nonzero = [
            [int(label), round(float(value), 4)]
            for label, value in enumerate(row)
            if abs(value) > prune_below and round(float(value), 4) != 0.0
        ]
        if nonzero:
            stored[key] = nonzero
            entries += len(nonzero)
    model: dict[str, Any] = {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "feature_set": FEATURE_SET,
        "labels": tags,
        "start": [round(float(v), 4) for v in best["start"]],
        "transitions": [[round(float(v), 4) for v in row] for row in best["transitions"]],
        "weights": dict(sorted(stored.items())),
        "calibration": None,
        "metadata": {
            **dict(metadata or {}),
            "algorithm": "averaged structured perceptron, first-order BIO transitions",
            "feature_hashing": "keyed BLAKE2b-64; no plaintext feature strings",
            "min_feature_docs": min_feature_docs,
            "selected_epoch": best["epoch"],
            "seed": seed,
            "entity_types": kinds,
        },
    }
    # Calibrate with the shipped pure-Python inference path, on validation only.
    tagger = SpanTagger(model)
    margins: list[float] = []
    outcomes: list[int] = []
    for example in validation:
        gold = {(s.entity_type, s.start, s.end) for s in example.spans}
        for span in tagger.predict(example.text):
            margins.append(math.log1p(span.margin))
            outcomes.append(int((span.entity_type, span.start, span.end) in gold))
    if margins and 0 < sum(outcomes) < len(outcomes):
        a, b = fit_platt(margins, outcomes)
        model["calibration"] = {
            "method": "platt",
            "feature": "log1p_margin",
            "a": round(a, 6),
            "b": round(b, 6),
            "fitted_on": "validation",
            "target": "exact span (type and boundaries) correctness",
            "spans": len(margins),
        }
    report = {
        "labels": tags,
        "train_documents": len(train_docs),
        "validation_documents": len(validation_docs),
        "train_tokens": int(sum(doc[2].size for doc in train_docs)),
        "features_kept": len(features),
        "stored_features": len(stored),
        "stored_weight_entries": entries,
        "prune_below": prune_below,
        "min_feature_docs": min_feature_docs,
        "train_alignment": train_stats,
        "validation_alignment": validation_stats,
        "history": history,
        "selected_epoch": best["epoch"],
        "selected_validation_exact_f1": best["f1"],
        "calibration": model["calibration"],
        "seconds": round(time.perf_counter() - started, 3),
    }
    return model, report


__all__ = ["fit_platt", "train_span_tagger"]
