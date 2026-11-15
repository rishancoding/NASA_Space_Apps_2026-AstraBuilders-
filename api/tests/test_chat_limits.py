"""Public chat must never fall through to a paid provider without configured deployment protection."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from api import chat_limits
from api.main import app

client = TestClient(app)
PAYLOAD = {'messages': [{'role': 'user', 'content': 'Show BASS evidence'}]}


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.setenv('CHAT_FIREWALL_PROTECTED', '1')
    provider = Mock(return_value={'answer': 'NASA evidence'})
    monkeypatch.setattr('api.main.chat', provider)
    return provider


def test_protected_deployment_can_call_provider(protected):
    assert client.post('/api/chat', json=PAYLOAD).status_code == 200
    protected.assert_called_once()


@pytest.mark.parametrize('platform,flag', [('1', ''), ('', '1'), ('', '')])
def test_missing_protection_fails_closed_even_with_spoofed_headers(monkeypatch, protected, platform, flag):
    monkeypatch.setenv('VERCEL', platform)
    monkeypatch.setenv('CHAT_FIREWALL_PROTECTED', flag)
    response = client.post('/api/chat', json=PAYLOAD, headers={'CHAT_FIREWALL_PROTECTED': '1', 'VERCEL': '1'})
    assert response.status_code == 503
    protected.assert_not_called()


def test_oversized_and_invalid_requests_never_call_provider(protected):
    assert client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'x' * 4001}]}).status_code == 422
    assert client.post('/api/chat', json={'messages': []}).status_code == 422
    assert client.post('/api/chat', content=(b'x' * 13000 for _ in range(2))).status_code == 413
    protected.assert_not_called()


def test_tool_loop_cannot_exceed_reserved_model_call_budget(monkeypatch):
    from types import SimpleNamespace as NS
    from api import agent
    model = Mock()
    model.chat.completions.create.return_value = NS(choices=[NS(message=NS(content='', tool_calls=[
        NS(id='step', function=NS(name='model_metrics', arguments='{}'))]), finish_reason='tool_calls')])
    monkeypatch.setattr(agent, '_record', lambda *args: ('{}', False))
    result = agent._chat_deepseek(PAYLOAD['messages'], client=model)
    assert result['stop_reason'] == 'max_rounds'
    assert model.chat.completions.create.call_count == 3
    assert all(call.kwargs['max_tokens'] == 1200 for call in model.chat.completions.create.call_args_list)
