from dataclasses import dataclass
from typing import Any, Callable

from app.services.units import UnitNormalizer


@dataclass(frozen=True)
class ReconciliationDecision:
    value: Any
    unit: str | None
    source_id: str | None
    confidence: float
    reason: str
    audit: dict[str, Any]


class WeightedVotingReconciler:
    AUTHORITY_WEIGHTS = {1: 1.0, 2: 0.75, 3: 0.5}

    def __init__(self, normalizer: UnitNormalizer | None = None, tie_margin: float = 0.03):
        self.normalizer = normalizer or UnitNormalizer()
        self.tie_margin = tie_margin

    def reconcile(
        self,
        field_name: str,
        candidates: list[dict[str, Any]],
        tie_breaker: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
    ) -> ReconciliationDecision | None:
        usable = [candidate for candidate in candidates if candidate.get("value") is not None]
        if not usable:
            return None
        groups: dict[str, dict[str, Any]] = {}
        for candidate in usable:
            key = self.normalizer.comparison_key(field_name, candidate.get("value"), candidate.get("unit"))
            group = groups.setdefault(key, {"candidates": [], "source_votes": {}})
            group["candidates"].append(candidate)
            source_key = candidate.get("source_id") or candidate.get("source_identifier") or "unknown"
            authority = self.AUTHORITY_WEIGHTS.get(int(candidate.get("authority_rank", 3)), 0.4)
            vote = authority * max(0.0, min(1.0, float(candidate.get("confidence", 0))))
            group["source_votes"][source_key] = max(vote, group["source_votes"].get(source_key, 0.0))

        ranked = []
        for key, group in groups.items():
            score = sum(group["source_votes"].values())
            best = min(
                group["candidates"],
                key=lambda candidate: (int(candidate.get("authority_rank", 3)), -float(candidate.get("confidence", 0))),
            )
            ranked.append((score, len(group["source_votes"]), key, best, group))
        ranked.sort(key=lambda item: (-item[0], -item[1], int(item[3].get("authority_rank", 3))))

        method = "weighted_source_vote"
        winner = ranked[0][3]
        if len(ranked) > 1 and abs(ranked[0][0] - ranked[1][0]) <= self.tie_margin and tie_breaker:
            winner = tie_breaker([ranked[0][3], ranked[1][3]])
            method = "weighted_vote_llm_tiebreak"
        total_score = sum(item[0] for item in ranked) or 1.0
        support_ratio = ranked[0][0] / total_score
        confidence = min(1.0, max(float(winner.get("confidence", 0)), support_ratio))
        audit_groups = [
            {
                "normalized_key": item[2],
                "score": round(item[0], 6),
                "source_count": item[1],
                "candidate_count": len(item[4]["candidates"]),
            }
            for item in ranked
        ]
        return ReconciliationDecision(
            value=winner.get("value"),
            unit=winner.get("unit"),
            source_id=winner.get("source_id"),
            confidence=confidence,
            reason=f"Selected by {method} using authority, confidence, and independent-source support.",
            audit={"method": method, "groups": audit_groups, "winner_support_ratio": round(support_ratio, 6)},
        )
