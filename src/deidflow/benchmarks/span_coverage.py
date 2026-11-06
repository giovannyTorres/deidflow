"""Diagnostic coverage and iterative one-to-one interval matching."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import deque

Span = tuple[int, int]


def _union(spans: set[Span]) -> list[Span]:
    result: list[Span] = []
    for start, end in sorted(spans):
        if result and start <= result[-1][1]:
            result[-1] = result[-1][0], max(end, result[-1][1])
        else:
            result.append((start, end))
    return result


def _overlap_matching(gold: set[Span], predicted: set[Span]) -> int:
    ceiling = min(len(gold), len(predicted))
    if len(gold & predicted) == ceiling:
        return ceiling
    targets, candidates = sorted(gold), sorted(predicted)
    starts = [start for start, _end in targets]
    owners: dict[int, int] = {}
    assigned: dict[int, int] = {}
    for origin in range(len(candidates)):
        pending = deque([origin])
        visited = {origin}
        parents: dict[int, int] = {}
        free = None
        while pending and free is None:
            candidate = pending.popleft()
            start, end = candidates[candidate]
            for target in range(bisect_left(starts, end)):
                if target in parents or targets[target][1] <= start:
                    continue
                parents[target] = candidate
                if target not in owners:
                    free = target
                    break
                previous = owners[target]
                if previous not in visited:
                    visited.add(previous)
                    pending.append(previous)
        if free is None:
            continue
        while True:
            candidate = parents[free]
            previous_target = assigned.get(candidate)
            owners[free], assigned[candidate] = candidate, free
            if previous_target is None:
                break
            free = previous_target
        if len(owners) == ceiling:
            break
    return len(owners)


def coverage_counts(gold: set[Span], predicted: set[Span]) -> dict[str, int]:
    union = _union(predicted)
    starts = [start for start, _end in union]
    prefix = [0]
    for start, end in union:
        prefix.append(prefix[-1] + end - start)

    def covered_before(position: int) -> int:
        index = bisect_right(starts, position) - 1
        if index < 0:
            return 0
        start, end = union[index]
        return prefix[index] + min(position - start, end - start)

    fully = partially = 0
    for start, end in gold:
        covered = covered_before(end) - covered_before(start)
        fully += covered == end - start
        partially += 0 < covered < end - start
    merged_gold = _union(gold)
    return {
        "known_gold_mentions": len(gold),
        "known_gold_characters": sum(end - start for start, end in merged_gold),
        "covered_gold_characters": sum(
            covered_before(end) - covered_before(start) for start, end in merged_gold
        ),
        "fully_covered_mentions": fully,
        "partially_covered_mentions": partially,
        "uncovered_mentions": len(gold) - fully - partially,
        "one_to_one_overlap_matches": _overlap_matching(gold, predicted),
    }
