from testbuilder.services.quality import similarity, structural_errors


def test_mcq_needs_two_options_and_a_correct_answer():
    assert structural_errors("mcq", {"options": [{"id": "a", "text": "x"}]})
    assert structural_errors(
        "mcq",
        {"options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
         "correct_option_ids": []},
    )
    # correct id must reference an existing option
    errors = structural_errors(
        "mcq",
        {"options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
         "correct_option_ids": ["z"]},
    )
    assert any("existing options" in e for e in errors)


def test_valid_mcq_passes():
    assert (
        structural_errors(
            "mcq",
            {"options": [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
             "correct_option_ids": ["a"]},
        )
        == []
    )


def test_coding_requires_cases_and_languages():
    errors = structural_errors("coding", {})
    assert any("test cases" in e for e in errors)
    assert any("allowed_languages" in e for e in errors)
    assert (
        structural_errors(
            "coding",
            {"allowed_languages": ["python"],
             "test_cases": [{"id": "t", "input": "1", "expected_output": "1"}]},
        )
        == []
    )


def test_text_requires_rubric_or_expected():
    assert structural_errors("text", {})
    assert structural_errors("text", {"rubric": "explain X"}) == []


def test_unknown_type_flagged():
    assert structural_errors("essay", {})


def test_similarity_detects_near_duplicates():
    assert similarity("What is a REST API?", "What is a REST API?") == 1.0
    assert similarity("What is a REST API?", "what is a rest api?") == 1.0  # case-insensitive
    assert similarity("What is a REST API?", "Explain binary search trees") < 0.5
