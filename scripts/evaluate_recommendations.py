from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.evidence_ranker import rank_evidence_candidates
from backend.services.recommendation_models import (
    CandidateAssessment,
    CravingIntent,
    EvidenceLink,
)

DEFAULT_CASES_PATH = PROJECT_ROOT / "evaluation" / "craving_cases.json"
TOP_K = 3


def run_evaluation(cases_path: Path = DEFAULT_CASES_PATH) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    totals = {
        "legacy": _empty_totals(),
        "evidence_grounded": _empty_totals(),
    }
    outputs: list[dict[str, Any]] = []

    for case in cases:
        intent, candidates, assessments, relevant = _build_case(case)
        legacy_ids = _legacy_restaurant_level_rank(intent, candidates)[:TOP_K]
        grounded_result = rank_evidence_candidates(intent, candidates, assessments)
        grounded_ids = [item["place_id"] for item in grounded_result["recommendations"]]

        _accumulate(
            totals["legacy"],
            legacy_ids,
            relevant,
            candidates,
            has_menu_evidence=False,
        )
        _accumulate(
            totals["evidence_grounded"],
            grounded_ids,
            relevant,
            candidates,
            has_menu_evidence=True,
        )
        outputs.append(
            {
                "id": case["id"],
                "query": case["query"],
                "relevant": sorted(relevant),
                "legacy_top3": legacy_ids,
                "evidence_grounded_top3": grounded_ids,
            }
        )

    metrics = {
        name: _finalize(values, len(cases))
        for name, values in totals.items()
    }
    return {
        "dataset": str(cases_path.relative_to(PROJECT_ROOT)),
        "cases": len(cases),
        "metrics": metrics,
        "outputs": outputs,
        "notes": {
            "legacy": (
                "Deterministic proxy for the old information boundary: restaurant-level "
                "aggregate traits plus rating, forced to three results, with no menu evidence."
            ),
            "evidence_grounded": (
                "Production constraint/evidence scorer over labeled dish evidence; intent "
                "and evidence labels are human-authored, so this does not evaluate live "
                "provider coverage or LLM intent extraction."
            ),
        },
    }


def _build_case(
    case: dict[str, Any],
) -> tuple[CravingIntent, list[dict[str, Any]], list[CandidateAssessment], set[str]]:
    constraints = []
    for index, raw in enumerate(case["constraints"], start=1):
        constraints.append({"id": f"c{index}", **raw})
    include_ids = [
        item["id"] for item in constraints if item["polarity"] == "include"
    ]
    intent = CravingIntent.model_validate(
        {
            "summary": case["query"],
            "constraints": constraints,
            "candidate_dishes": case["positive_dishes"],
            "search_queries": [
                {"text": case["query"], "constraint_ids": include_ids}
            ],
        }
    )

    candidates: list[dict[str, Any]] = []
    assessments: list[CandidateAssessment] = []
    relevant: set[str] = set()

    for suffix, rating, dish in (
        ("match_a", 4.2, case["positive_dishes"][0]),
        ("match_b", 4.1, case["positive_dishes"][1]),
    ):
        place_id = f"{case['id']}:{suffix}"
        relevant.add(place_id)
        candidate, assessment = _make_candidate(
            place_id,
            dish_entries=[(dish, include_ids, [])],
            restaurant_traits=[
                item["value"] for item in constraints if item["polarity"] == "include"
            ],
            rating=rating,
        )
        candidates.append(candidate)
        assessments.append(assessment)

    trap_entries: list[tuple[str, list[str], list[str]]] = []
    if len(include_ids) > 1:
        for index, constraint_id in enumerate(include_ids, start=1):
            trap_entries.append((f"Separate dish {index}", [constraint_id], []))
    trap, trap_assessment = _make_candidate(
        f"{case['id']}:aggregate_trap",
        dish_entries=trap_entries,
        restaurant_traits=[
            item["value"] for item in constraints if item["polarity"] == "include"
        ],
        rating=4.9,
    )
    candidates.append(trap)
    assessments.append(trap_assessment)

    partial_entries = (
        [("Popular partial match", [include_ids[0]], [])]
        if len(include_ids) > 1
        else []
    )
    partial, partial_assessment = _make_candidate(
        f"{case['id']}:partial",
        dish_entries=partial_entries,
        restaurant_traits=[constraints[0]["value"]] if len(include_ids) > 1 else [],
        rating=4.95,
    )
    candidates.append(partial)
    assessments.append(partial_assessment)

    popular, popular_assessment = _make_candidate(
        f"{case['id']}:popular_irrelevant",
        dish_entries=[],
        restaurant_traits=[],
        rating=5.0,
    )
    candidates.append(popular)
    assessments.append(popular_assessment)
    return intent, candidates, assessments, relevant


def _make_candidate(
    place_id: str,
    *,
    dish_entries: list[tuple[str, list[str], list[str]]],
    restaurant_traits: list[str],
    rating: float,
) -> tuple[dict[str, Any], CandidateAssessment]:
    evidence: list[dict[str, Any]] = []
    links: list[EvidenceLink] = []
    for index, (dish, supports, violates) in enumerate(dish_entries, start=1):
        evidence_id = f"{place_id}:e{index}"
        evidence.append(
            {
                "id": evidence_id,
                "kind": "official_menu",
                "label": dish,
                "detail": "Labeled evaluation dish.",
                "source_url": "https://evaluation.invalid/menu",
                "quality": 1.0,
                "declared_constraint_ids": [],
                "retrieval_rank": None,
            }
        )
        if supports:
            links.append(
                EvidenceLink(
                    evidence_id=evidence_id,
                    constraint_ids=supports,
                    stance="supports",
                )
            )
        if violates:
            links.append(
                EvidenceLink(
                    evidence_id=evidence_id,
                    constraint_ids=violates,
                    stance="violates",
                )
            )
    return (
        {
            "place_id": place_id,
            "name": place_id.replace(":", " ").title(),
            "rating": rating,
            "address": "Evaluation fixture",
            "lat": 43.5,
            "lng": -79.7,
            "restaurant_traits": restaurant_traits,
            "evidence": evidence,
        },
        CandidateAssessment(place_id=place_id, links=links),
    )


def _legacy_restaurant_level_rank(
    intent: CravingIntent,
    candidates: list[dict[str, Any]],
) -> list[str]:
    include = [item for item in intent.constraints if item.polarity == "include"]
    total_weight = sum(_weight(item.strength) for item in include) or 1

    def score(candidate: dict[str, Any]) -> float:
        traits = set(candidate.get("restaurant_traits") or [])
        coverage = sum(
            _weight(item.strength) for item in include if item.value in traits
        ) / total_weight
        rating = max(0.0, min((float(candidate["rating"]) - 3) / 2, 1.0))
        return 0.4 * coverage + 0.6 * rating

    ranked = sorted(candidates, key=score, reverse=True)
    return [item["place_id"] for item in ranked[:TOP_K]]


def _accumulate(
    totals: dict[str, float],
    ranked_ids: list[str],
    relevant: set[str],
    candidates: list[dict[str, Any]],
    *,
    has_menu_evidence: bool,
) -> None:
    top = ranked_ids[:TOP_K]
    hits = sum(item in relevant for item in top)
    totals["precision_at_3"] += hits / TOP_K
    totals["recall_at_3"] += hits / max(len(relevant), 1)
    totals["ndcg_at_3"] += _ndcg(top, relevant)
    candidate_by_id = {item["place_id"]: item for item in candidates}
    coherent = sum(item in relevant for item in top)
    denominator = max(len(top), 1)
    totals["constraint_satisfaction_rate"] += coherent / denominator
    totals["strong_item_rate"] += coherent / denominator
    totals["unsupported_claim_rate"] += (len(top) - coherent) / denominator
    totals["menu_evidence_coverage"] += (
        sum(bool(candidate_by_id[item].get("evidence")) for item in top) / denominator
        if has_menu_evidence
        else 0.0
    )
    totals["returned"] += len(top)


def _ndcg(ranked: list[str], relevant: set[str]) -> float:
    dcg = sum(
        (1.0 if item in relevant else 0.0) / math.log2(index + 2)
        for index, item in enumerate(ranked[:TOP_K])
    )
    ideal_hits = min(len(relevant), TOP_K)
    ideal = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return dcg / ideal if ideal else 0.0


def _empty_totals() -> dict[str, float]:
    return {
        "precision_at_3": 0.0,
        "recall_at_3": 0.0,
        "ndcg_at_3": 0.0,
        "constraint_satisfaction_rate": 0.0,
        "unsupported_claim_rate": 0.0,
        "menu_evidence_coverage": 0.0,
        "strong_item_rate": 0.0,
        "returned": 0.0,
    }


def _finalize(values: dict[str, float], case_count: int) -> dict[str, float]:
    return {
        key: round(value / case_count, 4) if key != "returned" else round(value / case_count, 2)
        for key, value in values.items()
    }


def _weight(strength: str) -> float:
    return {"required": 4.0, "strong": 3.0, "preferred": 2.0, "weak": 1.0}[strength]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline CraveAI ranking evaluation.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report.")
    args = parser.parse_args()
    report = run_evaluation(args.cases)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"Cases: {report['cases']} ({report['dataset']})")
    for name, metrics in report["metrics"].items():
        print(name)
        for metric, value in metrics.items():
            print(f"  {metric}: {value}")


if __name__ == "__main__":
    main()
