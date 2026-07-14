from testbuilder.services import ratelimit


def setup_function():
    ratelimit.reset_for_tests()


def test_limit_enforced_and_isolated_per_key():
    for _ in range(10):
        assert ratelimit.allow("run:a", 10)
    assert not ratelimit.allow("run:a", 10)  # 11th blocked (FR-067)
    assert ratelimit.allow("run:b", 10)  # other candidates unaffected


def test_window_slides(monkeypatch):
    import itertools

    clock = itertools.count(start=0, step=30).__next__
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: float(clock()))
    assert ratelimit.allow("k", 2)  # t=0
    assert ratelimit.allow("k", 2)  # t=30
    assert ratelimit.allow("k", 2)  # t=60 -> t=0 aged out
