from types import SimpleNamespace

from testbuilder.services import ai


def test_report_summary_uses_pro_model(monkeypatch):
    settings = SimpleNamespace(
        gemini_api_key="configured",
        gemini_report_model="gemini-2.5-pro",
    )
    used = {}

    monkeypatch.setattr(ai, "get_settings", lambda: settings)

    def fake_json(prompt, *, model=None):
        used["model"] = model
        return {"summary": "Clear strengths and weaknesses."}

    monkeypatch.setattr(ai, "_gemini_json", fake_json)

    summary = ai.summarize_performance({"overall_score": 80, "overall_max": 100})

    assert used["model"] == "gemini-2.5-pro"
    assert summary == "[AI-generated] Clear strengths and weaknesses."
