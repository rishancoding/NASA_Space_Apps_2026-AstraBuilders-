"""Atomic, shared chat quotas. No process-local fallback on public deployments."""
import hashlib
import hmac
import os
import time

import httpx
from fastapi import HTTPException, Request

MAX_CHAT_BYTES = 24000

# Check every counter before incrementing any. The lifetime counter has no TTL.
RESERVE = """
for i, key in ipairs(KEYS) do
  if tonumber(redis.call('GET', key) or '0') >= tonumber(ARGV[i]) then
    return 0
  end
end
for i, key in ipairs(KEYS) do
  redis.call('INCR', key)
  if i == 1 then redis.call('EXPIRE', key, 1200) end
  if i == 2 then redis.call('EXPIRE', key, 172800) end
end
return 1
"""


def configured():
    return all(os.getenv(k) for k in (
        'UPSTASH_REDIS_REST_URL', 'UPSTASH_REDIS_REST_TOKEN', 'CHAT_LIMIT_SECRET'))


def reserve_chat(request: Request):
    if not configured():
        raise HTTPException(503, 'AI chat is paused until shared usage protection is configured. The data tools remain available.')
    # Only trust Vercel's overwritten forwarding header when actually on Vercel.
    address = (request.headers.get('x-vercel-forwarded-for', 'unknown') if os.getenv('VERCEL')
               else request.client.host if request.client else 'unknown')
    digest = hmac.new(os.environ['CHAT_LIMIT_SECRET'].encode(), address.encode(), hashlib.sha256).hexdigest()
    now = int(time.time())
    keys = [f'thermaguard:chat:ip:{digest}:{now // 600}',
            f'thermaguard:chat:day:{now // 86400}', 'thermaguard:chat:lifetime']
    try:
        url = os.environ['UPSTASH_REDIS_REST_URL']
        if not url.startswith('https://'):
            raise ValueError('HTTPS required')
        response = httpx.post(url, headers={'Authorization': 'Bearer ' + os.environ['UPSTASH_REDIS_REST_TOKEN']},
                              json=['EVAL', RESERVE, '3', *keys,
                                    str(int(os.getenv('CHAT_PER_IP_10_MIN', '3'))),
                                    str(int(os.getenv('CHAT_DAILY_LIMIT', '20'))),
                                    str(int(os.getenv('CHAT_LIFETIME_LIMIT', '500')))], timeout=5)
        response.raise_for_status()
        result = response.json()['result']
        if type(result) is not int or result not in (0, 1):
            raise ValueError('Invalid quota response')
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'AI chat is temporarily paused because usage protection is unavailable.') from None
    if result == 0:
        raise HTTPException(429, 'AI chat has reached its usage limit. Try later; the data tools remain available.',
                            headers={'Retry-After': '600'})
