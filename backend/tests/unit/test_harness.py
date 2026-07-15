from testbuilder.services import harness

SIG = {
    "function_name": "twoSum",
    "params": [{"name": "nums", "type": "int[]"}, {"name": "target", "type": "int"}],
    "return_type": "int[]",
}


def test_signature_validation():
    assert harness.validate_signature(SIG) == []
    assert harness.validate_signature(None)
    assert harness.validate_signature({"function_name": "f", "params": [],
                                       "return_type": "int"})
    bad = harness.validate_signature(
        {"function_name": "f", "params": [{"name": "x", "type": "bigint"}],
         "return_type": "int"}
    )
    assert any("type must be one of" in e for e in bad)


def test_languages_supporting_restricts_java_cpp_on_unsupported_types():
    all_langs = harness.languages_supporting(SIG)
    assert set(all_langs) == {"python", "javascript", "java", "cpp"}
    # 2-D string arrays: only python/js
    sig2 = {"function_name": "f", "params": [{"name": "g", "type": "string[][]"}],
            "return_type": "int"}
    assert harness.languages_supporting(sig2) == ["python", "javascript"]


def test_starter_code_python_and_js():
    py = harness.starter_code(SIG, "python")
    assert "class Solution:" in py and "def twoSum(self, nums: List[int], target: int)" in py
    js = harness.starter_code(SIG, "javascript")
    assert "var twoSum = function(nums, target)" in js


def test_starter_code_java_cpp():
    java = harness.starter_code(SIG, "java")
    assert "class Solution" in java and "int[] twoSum(int[] nums, int target)" in java
    cpp = harness.starter_code(SIG, "cpp")
    assert "vector<int> twoSum(vector<int> nums, int target)" in cpp


def test_build_program_appends_driver():
    prog = harness.build_program(SIG, "python", "class Solution:\n    pass")
    assert prog.startswith("class Solution:")
    assert "_tb_main()" in prog


def test_stdin_and_parse_roundtrip():
    assert harness.stdin_for_args([[2, 7, 11, 15], 9]) == "[2,7,11,15]\n9"
    assert harness.parse_custom_input("[2,7,11,15]\n9", 2) == [[2, 7, 11, 15], 9]
    assert harness.parse_custom_input("[2,7]", 2) is None  # too few
    assert harness.parse_custom_input("not json\n9", 2) is None


def test_outputs_equal_structural_and_tolerant():
    assert harness.outputs_equal("[0,1]", [0, 1])
    assert not harness.outputs_equal("[1,0]", [0, 1])
    assert harness.outputs_equal("1.0000001", 1.0)  # float tolerance
    assert harness.outputs_equal("true", True)
    assert not harness.outputs_equal("true", 1)  # bool vs int distinct
    assert not harness.outputs_equal("garbage", [0, 1])


def test_autofill_generates_starter_and_restricts_languages():
    config = {"signature": SIG, "allowed_languages": ["python", "javascript", "java", "cpp"],
              "test_cases": []}
    filled = harness.autofill_coding_config(config)
    assert set(filled["starter_code"]) == {"python", "javascript", "java", "cpp"}
    assert filled["time_limit_ms"] == 5000

    sig2 = {"function_name": "f", "params": [{"name": "g", "type": "string[][]"}],
            "return_type": "int"}
    config2 = harness.autofill_coding_config({"signature": sig2,
                                              "allowed_languages": ["python", "java"]})
    # java dropped because it can't execute string[][]
    assert config2["allowed_languages"] == ["python"]
