"""AI Research Assistant: DeepSeek with the read-only tools in tools.py.

The model decides which tools to call (curated lookups, read-only SQL over the
SQLite copy of data/clean/, model predictions with reliability reviews); our
code runs them; the model writes the answer from the results and cites the
provenance each result carries. Calls DeepSeek's Anthropic-compatible Messages endpoint
through the `anthropic` SDK. Requires DEEPSEEK_API_KEY (environment, or a gitignored .env at
the repo root). Without one, `offline_answer` returns retrieval results.
"""
from __future__ import annotations

import json
import os

from . import db, evidence
from .tools import TOOLS, run_tool, to_json

MODEL = os.environ.get("FIRESAFE_MODEL", "deepseek-v4-pro")
BASE_URL = os.environ.get("FIRESAFE_BASE_URL", "https://api.deepseek.com/anthropic")
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _load_env_file(path: str = ENV_FILE) -> None:
    """Read KEY=VALUE lines from the local .env (gitignored) without overriding the real environment."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()
MAX_TOOL_ROUNDS = 8

SYSTEM_RULES = """You are the research assistant inside FireSafe, a tool that helps spacecraft engineers and \
researchers interpret NASA Physical Sciences Informatics (PSI) microgravity combustion data. Users ask in natural \
language; you answer in natural language, grounded in the data.

How to work:
- Answer only from tool results. Call tools before answering any factual question; never state a number, test \
outcome, prediction or citation that a tool did not return.
- Prefer the curated tools (find_tests, material_summary, condition_trends, search_nasa_documents, ...). When none \
fits, use query_database with one SELECT on the schema below. Do every calculation in SQL (COUNT, SUM, AVG, MIN, \
MAX, GROUP BY) rather than in your head; only simple counting of returned rows is allowed outside SQL. If a query \
errors, fix it and retry. Use describe_database before querying a src_* table.
- For predictions, call predict_sustained_burning (solid materials), predict_droplet_extinction (FLEX droplets) or \
prediction_sweep (how a probability changes across one input). Map the user's words onto the tool inputs and state \
any value you assumed (e.g. airflow 10 cm/s, ongoing-burn scenario, 3 mm droplet).
- Data scope: BASS (PSI-26) and BASS-II (PSI-25) solid tests (250), Saffire I-III (PSI-98/99/100) large burns, \
FLEX droplets (PSI-69), metadata/documents for 19 PSI investigations, original NASA tables for those \
investigations, and Earth-gravity ground thresholds (NTRS 20110008636, external to PSI, comparison only).

Data rules (the SQL database follows them; your answers must too):
- NULL means missing, never zero. AVG/SUM ignore NULLs, so report how many rows had a value (COUNT(col)) next to \
any average. A recorded 0 is a real zero.
- airflow_raw, fan_display_raw and other *_raw columns are verbatim text: do not average or parse them. Use \
airflow_readings.airflow_display_cm_s (reading_status = 'exact_display') for numeric airflow. BASS-II "Fan \
display" is not airspeed.
- burned_binary means any flame was seen (including brief ignition), not sustained burning. Sustained-flame labels \
are in solid_stage_training / solid_stage_observations (sustained_flame_binary). Extinction after a burn, hardware \
failure and fuel exhaustion are not "did not burn".
- Never pool FLEX droplets with solids. Never treat Earth-gravity ground thresholds as orbital outcomes.
- src_* tables keep NASA's original cells as TEXT, including note rows and typos: CAST only after checking values, \
and quote them as published.
- Outcome labels were AI-reviewed from crew/report notes without human sign-off; say so when they matter.
- Passages marked "Experiment PLAN" describe proposed tests: never present them as results.
- Never claim one material is safer than another unless a tool result marks that comparison as supported. Never \
present a ranking or prediction as a safety certification.
- Lunar/Martian gravity and pressures away from ~1 atm were never tested; say what cannot be answered rather than \
extrapolate.

Every tool result has a `provenance` block (datasets/tables and files, investigations with name and URL, model \
files, documents, SQL). Every prediction has a `reliability` review (or `model_statistics` for a sweep).

Write for an engineer, in Markdown, with these sections:
**Answer** - a direct, clear explanation in plain language.
**Supporting NASA evidence** - the experiments and key numbers, each with an inline citation such as \
[PSI-25 BASS-II test B8], [PSI-69 FLEX, PSI-69_Experimental table_FLEX.csv row 209] or \
[PSI-26 doc: <file>, <locator>].
**Prediction reliability** - REQUIRED whenever you made a prediction; omit otherwise. Give: the probability and \
predicted outcome; the reliability rating and every failed check with its numbers; the deployed model's \
out-of-fold ROC AUC and log loss next to the constant baseline and the simpler model; local calibration (observed \
rate among similar out-of-fold predictions, with n); the training rows for this material/fuel; every out-of-range \
warning; and 2-3 of the nearest real NASA tests with their observed outcomes. If the rating is low, say plainly \
that the estimate should not be relied on.
**Sources** - REQUIRED. List every dataset (table and file), every investigation (PSI id, name, URL) and every \
document locator or model file the answer used, taken from the provenance blocks. If you used query_database, \
include the SQL in a code block.
**Limitations and research gaps** - what the data does not cover or cannot support.
Keep it concise. The app also lists source links and draws charts from your tool results."""


def system_prompt() -> str:
    """Rules plus the live database schema (built from data/clean/, so it never drifts)."""
    return SYSTEM_RULES + "\n\nSQLite schema for query_database:\n" + db.schema_text()


def has_credentials() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)


def ask(messages: list, advisor_context: dict | None = None, on_tool=None) -> dict:
    """Run one user turn. `messages` is the running history (mutated in place: assistant
    turns and tool results are appended exactly as the API returned them).

    Returns {"text", "tool_calls": [(name, args, result)], "stop_reason"}.
    """
    import anthropic

    client = _client()
    calls = []
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=system_prompt(),
                tools=TOOLS,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            return {"text": "The DeepSeek API key was rejected. Check DEEPSEEK_API_KEY.", "tool_calls": calls,
                    "stop_reason": "error"}
        except anthropic.RateLimitError:
            return {"text": "Rate limited by the DeepSeek API. Wait a moment and try again.", "tool_calls": calls,
                    "stop_reason": "error"}
        except anthropic.APIStatusError as e:
            return {"text": f"DeepSeek API error {e.status_code}: {e.message}", "tool_calls": calls,
                    "stop_reason": "error"}
        except anthropic.APIConnectionError:
            return {"text": "Could not reach the DeepSeek API (network error).", "tool_calls": calls,
                    "stop_reason": "error"}

        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "refusal":
            return {"text": "The model declined this request.", "tool_calls": calls, "stop_reason": "refusal"}
        if resp.stop_reason == "pause_turn":
            continue
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not uses:
            text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
            if resp.stop_reason == "max_tokens":
                text += "\n\n_(Answer cut off at the length limit.)_"
            return {"text": text, "tool_calls": calls, "stop_reason": resp.stop_reason}
        results = []
        for u in uses:
            args = u.input if isinstance(u.input, dict) else json.loads(u.input or "{}")
            if on_tool:
                on_tool(u.name, args)
            try:
                out = run_tool(u.name, args, advisor_context)
                err = "error" in out
            except Exception as e:  # tool bug or bad argument: report it to the model, don't crash the chat
                out, err = {"error": f"{type(e).__name__}: {e}"}, True
            calls.append((u.name, args, out))
            results.append({"type": "tool_result", "tool_use_id": u.id, "content": to_json(out), "is_error": err})
        messages.append({"role": "user", "content": results})
    return {"text": "Stopped after too many tool calls without a final answer.", "tool_calls": calls,
            "stop_reason": "tool_limit"}


def offline_answer(question: str) -> dict:
    """No LLM configured: return the most relevant NASA passages, unsummarised."""
    hits = evidence.search(question, k=5)
    if not hits:
        return {"text": "No matching NASA passages found.", "tool_calls": []}
    parts = ["_No DeepSeek API key is configured, so these are the most relevant NASA passages, unsummarised._"]
    for h in hits:
        parts.append(f"**{h['investigation']} ({h['source_record']}) - {h['kind_label']}** "
                     f"({h['source_file']}, {h['locator']})\n\n> {h['text'][:600].strip()}")
    return {"text": "\n\n".join(parts), "tool_calls": [("search_nasa_documents", {"query": question},
                                                         {"results": hits})]}
