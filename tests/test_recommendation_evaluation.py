from scripts.evaluate_recommendations import run_evaluation


def test_offline_evaluation_improves_ranking_and_grounding_metrics():
    report = run_evaluation()
    legacy = report["metrics"]["legacy"]
    grounded = report["metrics"]["evidence_grounded"]

    assert report["cases"] == 20
    assert grounded["precision_at_3"] > legacy["precision_at_3"]
    assert grounded["ndcg_at_3"] > legacy["ndcg_at_3"]
    assert grounded["constraint_satisfaction_rate"] > legacy["constraint_satisfaction_rate"]
    assert grounded["unsupported_claim_rate"] == 0
    assert grounded["menu_evidence_coverage"] == 1


def test_spicy_soup_regression_excludes_aggregate_and_partial_traps():
    report = run_evaluation()
    case = next(item for item in report["outputs"] if item["id"] == "spicy_soup")

    assert case["evidence_grounded_top3"] == [
        "spicy_soup:match_a",
        "spicy_soup:match_b",
    ]
    assert "spicy_soup:aggregate_trap" in case["legacy_top3"]
    assert "spicy_soup:partial" in case["legacy_top3"]

