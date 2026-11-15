"""Page context is attached as data to the latest question, not as instructions."""
import json

from api import agent


def test_current_screen_context_survives_long_results_without_mutating_history():
    messages = [{"role": "user", "content": "Explain this result"}]
    context = {"page": "predictor", "page_text": "x" * 5000 + "Burn time: 8.4 seconds", "truncated": False}
    prepared = agent._prepare(messages, context)
    snapshot = prepared[-1]["content"].split("<dashboard_context>")[1].split("</dashboard_context>")[0]
    assert json.loads(snapshot) == context
    assert messages == [{"role": "user", "content": "Explain this result"}]


def test_context_off_does_not_reuse_a_previous_snapshot():
    messages = [{"role": "user", "content": "Explain this result"}]
    assert agent._prepare(messages, None) == messages
