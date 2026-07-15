from testbuilder.storage import evidence_prefix, slugify


def test_slugify_is_filesystem_safe():
    assert slugify("Backend Engineer Screening!") == "backend-engineer-screening"
    assert slugify("  Multiple   Spaces  ") == "multiple-spaces"
    assert slugify("") == "assessment"


def test_evidence_prefix_layout():
    prefix = evidence_prefix("Backend Screening", "abcdef1234567890", "Jane@Example.com",
                             "webcam")
    assert prefix == "backend-screening-abcdef12/jane@example.com/webcam"


def test_violation_prefix_uses_violations_subdir():
    prefix = evidence_prefix("DSA Round", "0011223344556677", "x@y.com", "violations")
    assert prefix == "dsa-round-00112233/x@y.com/violations"


def test_email_is_sanitized():
    prefix = evidence_prefix("T", "aaaaaaaa", "we ird/../name@x.com", "webcam")
    assert ".." not in prefix.split("/")[1]
    assert "/" not in prefix.split("/")[1]
