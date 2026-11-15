"""Public chat must never fall through to a paid provider without a reservation."""
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from api import chat_limits
from api.main import app

client = TestClient(app)
PAYLOAD = {'messages': [{'role': 'user', 'content': 'Show BASS evidence'}]}


@pytest.fixture
def protected(monkeypatch):
    monkeypatch.setenv('UPSTASH_REDIS_REST_URL', 'https://redis.example')
    monkeypatch.setenv('UPSTASH_REDIS_REST_TOKEN', 'private-redis-token')
    monkeypatch.setenv('CHAT_LIMIT_SECRET', 'private-hmac-secret')
    monkeypatch.setenv('VERCEL', '1')
    provider = Mock(return_value={'answer': 'NASA evidence'})
    monkeypatch.setattr('api.main.chat', provider)
    return provider


@pytest.mark.parametrize('result,status,paid_calls', [(1, 200, 1), (0, 429, 0), (None, 503, 0)])
def test_shared_reservation_gates_paid_calls(monkeypatch, protected, result, status, paid_calls):
    post = Mock(return_value=Mock(json=lambda: {'result': result}))
    monkeypatch.setattr(chat_limits.httpx, 'post', post)
    response = client.post('/api/chat', json=PAYLOAD, headers={'x-vercel-forwarded-for': '192.0.2.1'})
    assert response.status_code == status
    assert protected.call_count == paid_calls
    command = post.call_args.kwargs['json']
    assert command[0] == 'EVAL' and command[2] == '3'
    assert '192.0.2.1' not in str(command)
    assert 'private-' not in response.text


def test_store_outage_and_missing_config_fail_closed(monkeypatch, protected):
    monkeypatch.setattr(chat_limits.httpx, 'post', Mock(side_effect=httpx.ConnectError('private diagnostics')))
    assert client.post('/api/chat', json=PAYLOAD).status_code == 503
    monkeypatch.delenv('CHAT_LIMIT_SECRET')
    assert client.post('/api/chat', json=PAYLOAD).status_code == 503
    protected.assert_not_called()


def test_oversized_and_invalid_requests_never_reserve_or_call_provider(monkeypatch, protected):
    post = Mock()
    monkeypatch.setattr(chat_limits.httpx, 'post', post)
    assert client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'x' * 4001}]}).status_code == 422
    assert client.post('/api/chat', json={'messages': []}).status_code == 422
    assert client.post('/api/chat', content=(b'x' * 13000 for _ in range(2))).status_code == 413
    post.assert_not_called()
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
