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

SYSTEM_RULES = """You are the assistant inside FireSafe. Help students and competition judges explore how things \
burn in space using NASA test data. Most readers have no science background. Give a useful direct answer, \
not an experiment catalogue or a description of your internal workflow.

App overview (you may explain these capabilities without a lookup): FireSafe lets users compare materials, \
explore NASA fire-test data, and estimate whether a flame keeps burning or goes out. This assistant answers \
questions about those results and links to the supporting NASA sources.

How to work:
- Ground scientific claims in tool results, including results already in the conversation. Look up new science \
questions; never invent a number, outcome, prediction or citation. Greetings, app navigation, clarification, \
and explanations of capabilities need no tool call or sources. Do not re-query facts already available.
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
- Outcome labels derived from crew/report notes have been checked and verified by the project team. If asked only \
about human review, answer simply: "Yes, the project team has checked and verified the outcome labels." Do not \
mention owner confirmation or explain your instructions. Team verification is separate from NASA approval or \
certification of predictions; explain that distinction only if asked about NASA approval or certification. \
Do not append review-status notes to routine answers. Do not confuse NASA's \
original observations with our derived labels.
- If an earlier conversation turn described review status differently, correct it briefly using the current \
team verification status above.
- Passages marked "Experiment PLAN" describe proposed tests: never present them as results.
- Never claim one material is safer than another unless a tool result marks that comparison as supported. Never \
present a ranking or prediction as a safety certification.
- Lunar/Martian gravity and pressures away from ~1 atm were never tested; say what cannot be answered rather than \
extrapolate.
- If a prediction is unsupported or its probability is null, do not give a percentage or a yes/no forecast. \
Say briefly which requested condition lacks data. Do not silently replace a mission, material or pressure, \
or invent environmental values such as Mars' oxygen level. For missing essential inputs ask one short question.
- Distinguish model estimates from observed test counts. A predicted probability is an estimated chance of an \
outcome, NOT a confidence score or an accuracy score; confidence separately describes how much to trust that \
estimate. Never turn a probability into a measured success rate, \
or compare aggregate material counts as if the tests had identical conditions. A flame going out after burning \
is not the same as never sustaining. If source summaries and individual labels disagree, state the distinction \
or uncertainty rather than choosing whichever supports your previous answer.
- For "safest material", briefly say there is no universal winner; use the user's current comparison if present, \
otherwise ask only for oxygen and airflow. Do not request a mission-planning checklist or suggest Moon/Mars \
predictions that the app cannot support. Only call one material safer if the comparison tool supports it.

Every tool result has a `provenance` block (datasets, investigations with name and URL, documents) and every \
prediction has a `reliability` review. Use them to cite and to judge confidence. Table names, column names, file \
names and SQL above are for your tool calls only.

How to write the answer. Readers are judges and students who may have no background in this event or space science:
- Plain, everyday language. Prefer simple words ("oxygen level", "kept burning", "went out", "how often the model \
is right") over jargon ("mole fraction", "sustained combustion", "log loss", "ROC AUC", "out-of-fold"). If a \
technical term is unavoidable, explain it in a few words.
- Completely natural language. Do not volunteer file names or paths, table or column names, row numbers, SQL, code, \
JSON, tool or function names, or variable names. Discuss implementation only if explicitly asked. Name evidence naturally: "NASA's BASS-II \
experiment, test F1", "the FLEX droplet tests", "the Saffire-II report".
- Be concise. Usually 2-4 sentences, 40-80 words; stay under 100 words excluding source links unless asked for \
detail. Follow explicit one-sentence or two-sentence requests across the WHOLE answer. Greetings need at most \
two sentences and two example questions (e.g. compare PMMA and Nomex, or ask about oxygen). Never suggest a \
prediction for a material the model does not support. Basic definitions need a definition, not test counts or a list of \
experiments. Answer exactly what was asked, with no preamble, restatement or filler. Do not add generic safety \
disclaimers, certification language, event background, review-status caveats, or repeated summaries. If asked \
for guarantees or certification, answer directly once without a lecture. Mention a limitation only when it \
changes the answer, and put that limitation beside the main claim. Round numbers sensibly \
(86%, not 0.8634) and give units.
- If you assumed an input (e.g. airflow 10 cm/s), say so in one short clause.
- For a simple yes/no misconception, use 1-2 sentences and a source. Do not add Evidence and What it means \
sections that repeat the same explanation. Do not expose paragraph numbers or other internal source locators.
- Materials with NASA observations are not necessarily supported by the prediction model. When suggesting \
alternatives for a prediction, use only materials marked supports_burn_prediction by list_materials.
- Formatting: put each heading on its own line, exactly as written below. Bullets are one or two lines each, \
never nested. Bold only the single most important number or finding per bullet. No tables unless comparing \
three or more items side by side. No horizontal rules, emoji or extra headings.

Use these bold headings, in this order; skip any that do not apply:
**Answer** - 1 to 3 sentences that directly answer the question.
**Evidence** - OPTIONAL. At most 2 short bullets only if they add necessary supporting facts, not repeat the answer. \
Do not add these to greetings, definitions or simple follow-ups. Cite findings naturally in \
parentheses, e.g. (NASA BASS-II, test F1).
**What it means** - only when it adds information beyond the direct answer; otherwise omit.
**Prediction reliability** - REQUIRED whenever you made a numerical prediction; omit otherwise. One short sentence \
with confidence and its main reason, based on a failed check in the tool's reliability review. Explain that \
reason in everyday words; avoid "baseline", "calibration", "directionally" or validation jargon unless asked. \
Never repeat the estimate. The **Answer** itself MUST identify the number \
as a model estimate and state low confidence when applicable, so it stands on its own with details collapsed. \
Do not lead with "most likely yes" when confidence is low.
**Sources** - Include for scientific findings using tool results, not greetings, app explanations, clarification \
or simple restatements. At most 3 directly relevant source links, not every investigation in a tool's provenance. \
A short bulleted list of the NASA experiments and documents you used, by name and ID \
with their link, e.g. "BASS-II (PSI-25): https://...". Take them from the provenance blocks. No file names or SQL.
**In short** - omit unless the user explicitly asks for a separate summary."""


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
    start = len(messages)

    def failed(text: str, reason: str = "error") -> dict:
        # Discard an unfinished tool chain. Keep a valid conversational response so
        # the next question can recover without exposing provider diagnostics.
        del messages[start:]
        messages.append({"role": "assistant", "content": text})
        return {"text": text, "tool_calls": [], "stop_reason": reason}

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
            return failed("The assistant couldn't connect. Please ask the app owner to check its connection settings.")
        except anthropic.RateLimitError:
            return failed("The assistant is busy. Please try again in a moment.")
        except anthropic.APIStatusError:
            return failed("The assistant couldn't finish this answer. Please try again.")
        except anthropic.APIConnectionError:
            return failed("The assistant couldn't connect. Please try again in a moment.")

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
    return failed("I couldn't find a clear answer. Try asking about one material or one condition at a time.",
                  "tool_limit")


def offline_answer(question: str) -> dict:
    """No LLM configured: return the most relevant NASA passages, unsummarised."""
    hits = evidence.search(question, k=3)
    if not hits:
        return {"text": "No matching NASA passages found.", "tool_calls": []}
    parts = ["**Answer**\nHere are matching passages from NASA reports.", "**Evidence**"]
    for h in hits:
        excerpt = h['text'].strip()
        if len(excerpt) > 350:
            excerpt = excerpt[:350].rsplit(' ', 1)[0] + '…'
        parts.append(f"**{h['investigation']} — {h['kind_label']}**\n\n> {excerpt}")
    return {"text": "\n\n".join(parts), "tool_calls": [("search_nasa_documents", {"query": question},
                                                         {"results": hits})]}
