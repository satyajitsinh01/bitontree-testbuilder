from testbuilder.services.scoring import score_code_cases, score_mcq

MCQ = {"options": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
       "correct_option_ids": ["a", "c"]}


def test_mcq_exact_set_match_required():
    assert score_mcq(MCQ, {"selected_option_ids": ["a", "c"]}, 4.0) == 4.0
    assert score_mcq(MCQ, {"selected_option_ids": ["a"]}, 4.0) == 0.0  # partial = wrong
    assert score_mcq(MCQ, {"selected_option_ids": ["a", "b", "c"]}, 4.0) == 0.0


def test_mcq_unanswered_never_negative():
    """UT-M9-01: unanswered -> 0 even with negative marking on."""
    assert score_mcq(MCQ, {}, 4.0, negative_marks=1.0) == 0.0
    assert score_mcq(MCQ, {"selected_option_ids": []}, 4.0, negative_marks=1.0) == 0.0


def test_mcq_negative_marking_applies_to_wrong_answers():
    assert score_mcq(MCQ, {"selected_option_ids": ["b"]}, 4.0, negative_marks=1.0) == -1.0
    assert score_mcq(MCQ, {"selected_option_ids": ["b"]}, 4.0) == 0.0


CASES = [
    {"id": "t1", "weight": 2},
    {"id": "t2", "weight": 2},
    {"id": "t3", "weight": 1},
    {"id": "t4", "weight": 1},
    {"id": "t5", "weight": 1},
]


def test_weighted_partial_credit():
    """UT-M7-03: cases {t1,t2,t3} passing with weights {2,2,1} -> 5/7 of max."""
    results = [{"case_id": c, "passed": c in ("t1", "t2", "t3")} for c in
               ("t1", "t2", "t3", "t4", "t5")]
    assert score_code_cases(CASES, results, 7.0) == 5.0


def test_all_fail_and_all_pass():
    all_fail = [{"case_id": c["id"], "passed": False} for c in CASES]
    all_pass = [{"case_id": c["id"], "passed": True} for c in CASES]
    assert score_code_cases(CASES, all_fail, 7.0) == 0.0
    assert score_code_cases(CASES, all_pass, 7.0) == 7.0


def test_zero_weight_pool_scores_zero():
    assert score_code_cases([], [], 5.0) == 0.0
