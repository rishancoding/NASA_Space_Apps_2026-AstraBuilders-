"""Gate paid chat on the Vercel-native firewall configured for this deployment.

Counters live at Vercel's edge, never in a Python worker or an external database.
This is per-IP, per-region throttling, not an account-wide spending cap.
"""
import os

from fastapi import HTTPException, Request

MAX_CHAT_BYTES = 24000


def configured():
    return os.getenv("VERCEL") == "1" and os.getenv("CHAT_FIREWALL_PROTECTED") == "1"


def reserve_chat(request: Request):
    # Set this server-only flag only after publishing the matching WAF rule.
    # Do not accept a browser header, cookie, or request field as evidence.
    if not configured():
        raise HTTPException(503, "AI chat is paused until Vercel usage protection is enabled. The data tools remain available.")
