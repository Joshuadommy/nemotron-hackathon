"""Compliance Copilot — agent loop, LLM client, and tools.

Pipeline: scenario -> Nemotron decides which regulations may apply ->
fetches the full text of each candidate regulation -> cross-references
against the scenario -> emits a structured verdict with citations and
risk flags.

The `run_agent` generator yields trace events that the Streamlit UI can
render in real time:
  ("status", str)
  ("model_text", str)              # any narration the model produces between tool calls
  ("tool_call", {name, args, id})
  ("tool_result", {id, summary, payload})
  ("verdict", dict)                # final structured output
  ("usage", {prompt_tokens, completion_tokens, cost_usd})
  ("error", str)
"""
from __future__ import annotations

import json
import os
import re   # noqa: F401  — used by _extract_json_verdict below
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator, Iterable

from dotenv import load_dotenv
from openai import OpenAI

import cache

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"
INDEX_FILE = DATA_DIR / "index.md"

# Default to Nano for cost; users can override with COMPLIANCE_MODEL env var.
DEFAULT_MODEL = os.getenv("COMPLIANCE_MODEL", "hack-crusoe/Nemotron-3-Nano-30B-A3B-FP8")
NANO_INPUT_PER_M = 0.05
NANO_OUTPUT_PER_M = 0.20

# Generous enough for the model to fetch every regulation it wants (worst case
# 1 list + 7 get_regulation calls + 1 synthesis turn + slack) without the
# fallback path getting starved.
MAX_LOOP_STEPS = 14


# ──────────────────────────── corpus loader ─────────────────────────────

@dataclass(frozen=True)
class RegMeta:
    id: str
    file: str
    jurisdiction: str
    domain: str
    triggers: str
    signals: list[str]


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict[str, Any] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip()
    return meta, body


def load_index() -> list[RegMeta]:
    """Parse data/index.md and return a list of regulation metadata."""
    entries: list[RegMeta] = []
    if not INDEX_FILE.exists():
        return entries
    text = INDEX_FILE.read_text()
    _, body = _parse_frontmatter(text)
    current: dict[str, Any] = {}

    def flush() -> None:
        if not current.get("id"):
            return
        signals = current.get("signals", [])
        if isinstance(signals, str):
            try:
                signals = json.loads(signals)
            except json.JSONDecodeError:
                signals = [s.strip().strip('"') for s in signals.strip("[]").split(",")]
        entries.append(
            RegMeta(
                id=str(current.get("id", "")),
                file=str(current.get("file", "")),
                jurisdiction=str(current.get("jurisdiction", "")),
                domain=str(current.get("domain", "")),
                triggers=str(current.get("triggers", "")),
                signals=signals if isinstance(signals, list) else [],
            )
        )
        current.clear()

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("- id:"):
            flush()
            current["id"] = line.split(":", 1)[1].strip()
        elif line.startswith("  ") and ":" in line:
            k, _, v = line.strip().partition(":")
            v = v.strip()
            if k == "signals":
                try:
                    current[k] = json.loads(v)
                except json.JSONDecodeError:
                    current[k] = [s.strip().strip('"') for s in v.strip("[]").split(",") if s.strip()]
            else:
                current[k] = v
    flush()
    return entries


def load_regulation(reg_id: str) -> dict[str, Any] | None:
    """Return full regulation: {id, metadata, body, sections:[{heading, text}], file}."""
    for meta in load_index():
        if meta.id == reg_id:
            path = DATA_DIR / meta.file
            if not path.exists():
                return None
            raw = path.read_text()
            fm, body = _parse_frontmatter(raw)
            sections = _split_sections(body)
            return {
                "id": meta.id,
                "title": fm.get("title", meta.id),
                "jurisdiction": fm.get("jurisdiction", meta.jurisdiction),
                "effective": fm.get("effective", ""),
                "enforcement": fm.get("enforcement", ""),
                "penalties": fm.get("penalties", ""),
                "applies_when": fm.get("applies_when", ""),
                "file": meta.file,
                "sections": sections,
                "body": body,
            }
    return None


def _split_sections(body: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_heading: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_heading is not None:
                sections.append({"heading": current_heading, "text": "\n".join(buf).strip()})
            current_heading = line[3:].strip()
            buf = []
        else:
            buf.append(line)
    if current_heading is not None:
        sections.append({"heading": current_heading, "text": "\n".join(buf).strip()})
    return sections


# ──────────────────────────── tool definitions ──────────────────────────

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_regulations",
            "description": (
                "List every regulation in the local corpus. Returns each "
                "regulation's id, jurisdiction, domain, applicability trigger, "
                "and routing signals (keywords that suggest relevance). Call "
                "this FIRST to decide which regulations to pull in full."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_regulation",
            "description": (
                "Fetch the full text of a regulation by id (e.g., 'NYC_LL144'). "
                "Returns the title, jurisdiction, applicability rule, penalties, "
                "and every numbered section with its requirements. Call this "
                "for each regulation you flagged as potentially applicable."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reg_id": {
                        "type": "string",
                        "description": "Regulation id as listed by list_regulations (case-sensitive).",
                    }
                },
                "required": ["reg_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "emit_verdict",
            "description": (
                "Emit the FINAL compliance verdict. Call this exactly once, "
                "after you have analyzed every applicable regulation. Do not "
                "narrate the answer in plain text — put it all in this call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Two-to-four sentence executive summary of the compliance picture.",
                    },
                    "applicable_regulations": {
                        "type": "array",
                        "description": "Regulations that apply to this scenario.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reg_id": {"type": "string"},
                                "title": {"type": "string"},
                                "jurisdiction": {"type": "string"},
                                "why_applicable": {
                                    "type": "string",
                                    "description": "Short explanation tying the scenario to this regulation's scope.",
                                },
                            },
                            "required": ["reg_id", "title", "jurisdiction", "why_applicable"],
                        },
                    },
                    "requirements": {
                        "type": "array",
                        "description": "Concrete things the user must do to be compliant.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "requirement": {
                                    "type": "string",
                                    "description": "Imperative phrasing of what must be done.",
                                },
                                "citation": {
                                    "type": "string",
                                    "description": "Regulation id and section, e.g., 'NYC_LL144 §2'.",
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["must", "should", "watch"],
                                },
                                "rationale": {
                                    "type": "string",
                                    "description": "One short sentence explaining why this requirement applies to THIS scenario (not generic regulation text).",
                                },
                            },
                            "required": ["requirement", "citation", "priority"],
                        },
                    },
                    "risk_flags": {
                        "type": "array",
                        "description": "Specific risks, prohibitions, or disqualifying patterns spotted in the scenario.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "flag": {"type": "string"},
                                "citation": {"type": "string"},
                                "severity": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "rationale": {
                                    "type": "string",
                                    "description": "One short sentence explaining why this is a risk for THIS scenario.",
                                },
                            },
                            "required": ["flag", "citation", "severity"],
                        },
                    },
                    "cross_references": {
                        "type": "array",
                        "description": (
                            "Overlaps where a single workflow can satisfy multiple regulations "
                            "(e.g., one candidate notification process serving both NYC LL144 §3 "
                            "and GDPR Art.13). Surface only real overlaps — empty array if none."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "Short label for the shared workflow (e.g., 'Unified candidate notification').",
                                },
                                "involves": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Citation strings for the regulations this workflow covers.",
                                },
                                "note": {
                                    "type": "string",
                                    "description": "One sentence explaining how a single workflow satisfies all of them.",
                                },
                            },
                            "required": ["title", "involves", "note"],
                        },
                    },
                    "recommended_next_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "open_questions": {
                        "type": "array",
                        "description": "Information you would need to make a firmer call.",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "summary",
                    "applicable_regulations",
                    "requirements",
                    "risk_flags",
                    "recommended_next_steps",
                ],
            },
        },
    },
]


# ──────────────────────────── tool dispatch ─────────────────────────────

def _tool_list_regulations() -> dict[str, Any]:
    entries = load_index()
    return {
        "regulations": [
            {
                "id": m.id,
                "jurisdiction": m.jurisdiction,
                "domain": m.domain,
                "applies_when": m.triggers,
                "signals": m.signals,
            }
            for m in entries
        ]
    }


def _tool_get_regulation(reg_id: str) -> dict[str, Any]:
    reg = load_regulation(reg_id)
    if reg is None:
        return {"error": f"Unknown regulation '{reg_id}'. Use list_regulations to see valid ids."}
    return {
        "id": reg["id"],
        "title": reg["title"],
        "jurisdiction": reg["jurisdiction"],
        "effective": reg["effective"],
        "enforcement": reg["enforcement"],
        "penalties": reg["penalties"],
        "applies_when": reg["applies_when"],
        "sections": reg["sections"],
    }


def dispatch_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "list_regulations":
        return _tool_list_regulations()
    if name == "get_regulation":
        return _tool_get_regulation(args.get("reg_id", ""))
    return {"error": f"Unknown tool: {name}"}


def summarize_tool_result(name: str, result: dict[str, Any]) -> str:
    """Short human-readable line for the UI trace."""
    if name == "list_regulations":
        ids = [r["id"] for r in result.get("regulations", [])]
        return f"Loaded corpus index — {len(ids)} regulations available."
    if name == "get_regulation":
        if result.get("error"):
            return result["error"]
        secs = len(result.get("sections", []))
        return f"Pulled {result.get('id')} — {result.get('title')} ({secs} sections, {result.get('jurisdiction')})."
    return "Tool returned."


# ──────────────────────────── LLM client ────────────────────────────────

def make_client() -> OpenAI:
    key = os.getenv("CRUSOE_API_KEY")
    if not key:
        raise RuntimeError(
            "CRUSOE_API_KEY missing. Add it to .env or export it before running."
        )
    return OpenAI(
        api_key=key,
        base_url="https://api.inference.crusoecloud.com/v1",
    )


SYSTEM_PROMPT = """You are Compliance Copilot, a careful regulatory analyst focused on AI / automated-decision regulations in employment.

Your corpus covers seven regulations: NYC Local Law 144 (AEDT), EEOC Title VII guidance on AI hiring, GDPR, the EU AI Act, CCPA/CPRA, the Colorado AI Act, and the Illinois AI Video Interview Act.

═══ INPUT TRIAGE — DO THIS FIRST ═══
Before doing anything, decide which case the user's message falls into:

(A) A real business scenario about AI, automation, hiring, or employment that could plausibly touch one of those seven regulations.
(B) A greeting / smalltalk ("hi", "hello", "how are you").
(C) A meta-question ("what can you do?", "what is this?", "what regulations do you cover?").
(D) Off-topic — something this tool can't help with (general legal questions outside AI-and-employment, coding help, recipes, etc.).
(E) Too vague to act on (one or two ambiguous words, e.g., "compliance", "help me", "AI").

If (A), proceed with the workflow below.
If (B), (C), (D), or (E): DO NOT call any tools. Respond with one short paragraph (2-3 sentences max). For (B/C/E) invite the user to describe a real scenario — give a concrete example like "We're deploying an AI resume-screening tool for a NYC company". For (D) explain politely that you only cover AI-and-employment compliance and suggest they describe such a scenario instead. Keep it warm and brief. Do NOT pretend you analyzed regulations.

═══ WORKFLOW (only for case A) ═══
1. Call list_regulations to see the local corpus.
2. Decide which regulations may apply. Reason briefly.
3. Call get_regulation for EACH regulation that may apply.
4. Call emit_verdict EXACTLY ONCE with a structured compliance plan. Then stop.

Hard rules for case (A) only:
- The ONLY way to deliver your final answer is by calling emit_verdict. Do not write a markdown report or list requirements in plain text.
- Never cite a section you have not fetched.
- Citations must use the exact reg_id and section heading you saw (e.g., "NYC_LL144 §2. Bias Audit Requirement").
- Every requirement and risk_flag MUST include a one-sentence `rationale` explaining why this applies to the SPECIFIC scenario — not generic regulation text.
- If multiple regulations require similar workflows (e.g., candidate notification appears in NYC LL144 §3 AND GDPR Art.13), surface the overlap in `cross_references` so the user can satisfy both with one process. If there are no genuine overlaps, leave it as an empty array — do not invent them.
- Prefer to over-include relevant regulations rather than miss one.
- If facts are missing (jurisdiction, candidate residency, headcount, vendor), put them in `open_questions` inside emit_verdict — don't ask in plain text.
"""

FORCE_VERDICT_PROMPT = (
    "You wrote a plain-text answer instead of calling emit_verdict. "
    "Crusoe's tool-forcing path is unreliable, so instead: output a single "
    "JSON object — and NOTHING else — wrapped in a ```json ... ``` fenced "
    "block. The schema:\n"
    "{\n"
    '  "summary": "2-4 sentences",\n'
    '  "applicable_regulations": [{"reg_id":"NYC_LL144","title":"...","jurisdiction":"...","why_applicable":"..."}],\n'
    '  "requirements": [{"requirement":"...","citation":"NYC_LL144 §2. Bias Audit Requirement","priority":"must|should|watch","rationale":"why THIS scenario triggers it"}],\n'
    '  "risk_flags": [{"flag":"...","citation":"...","severity":"high|medium|low","rationale":"why this risk applies"}],\n'
    '  "cross_references": [{"title":"Unified candidate notification","involves":["NYC_LL144 §3","GDPR Art.13"],"note":"one workflow can serve both"}],\n'
    '  "recommended_next_steps": ["..."],\n'
    '  "open_questions": ["..."]\n'
    "}\n"
    "Populate every field from the regulations you already fetched. "
    "Citations must use the exact section headings you saw via get_regulation. "
    "cross_references is OPTIONAL — only include real overlaps where a single workflow "
    "satisfies multiple regulations, otherwise leave it as an empty array. "
    "Output ONLY the fenced JSON block — no preamble, no commentary."
)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


_SMART_QUOTES = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
})


def _repair_truncated_json(text: str) -> str | None:
    """Attempt to close an unterminated JSON object that ends mid-value.

    Walks the text tracking brace/bracket depth and string state. If we end
    inside a string, close it. If we're mid-value (just saw ':' or ','),
    insert null. Then append the missing ] and } in the right order.
    Returns the repaired string, or None if no { was found at all.
    """
    start = text.find("{")
    if start < 0:
        return None
    s = text[start:]

    stack: list[str] = []   # 'o' = object, 'a' = array
    in_str = False
    esc = False
    after_colon = False     # last non-space was ':' (expecting value)
    last_significant = ""   # last non-space char outside string

    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                last_significant = '"'
            continue
        if ch == '"':
            in_str = True
            after_colon = False
            last_significant = '"'
            continue
        if ch.isspace():
            continue
        if ch == "{":
            stack.append("o")
            after_colon = False
        elif ch == "[":
            stack.append("a")
            after_colon = False
        elif ch == "}":
            if stack and stack[-1] == "o":
                stack.pop()
            after_colon = False
        elif ch == "]":
            if stack and stack[-1] == "a":
                stack.pop()
            after_colon = False
        elif ch == ":":
            after_colon = True
        elif ch == ",":
            after_colon = False
        last_significant = ch

    if not stack and not in_str:
        return s   # already balanced
    repaired = s
    if in_str:
        repaired += '"'
    # If we ended right after a ':' or ',' we need a value placeholder
    if after_colon or last_significant == ",":
        repaired += " null"
    # Close everything in reverse order
    while stack:
        kind = stack.pop()
        repaired += "}" if kind == "o" else "]"
    return repaired


def _balanced_objects(text: str):
    """Yield every balanced { ... } substring in text. Skips braces inside
    strings so {"x":"}"} parses correctly."""
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        in_str = False
        esc = False
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        yield text[i : j + 1]
                        break
            j += 1
        i = j + 1


def _extract_json_verdict(text: str) -> dict[str, Any] | None:
    """Pull a JSON verdict out of free-form model output.

    Strategy, in order:
      1. Try every ```json...``` fenced block.
      2. Try every balanced {...} substring.
      3. Try a brace-repaired version of the whole text (covers the common
         failure where the model ran out of tokens mid-JSON).

    Each candidate is normalized for smart-quote characters before parsing.
    Candidates are scored by how many expected fields they contain; the
    best-scoring valid object wins.
    """
    if not text:
        return None

    normalized = text.translate(_SMART_QUOTES)

    candidates: list[str] = []
    for m in _FENCE_RE.finditer(normalized):
        candidates.append(m.group(1).strip())
    candidates.extend(_balanced_objects(normalized))
    repaired = _repair_truncated_json(normalized)
    if repaired:
        candidates.append(repaired)

    expected = ("summary", "applicable_regulations", "requirements", "risk_flags")
    best: tuple[int, dict] | None = None
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        score = sum(1 for k in expected if obj.get(k))
        if best is None or score > best[0]:
            best = (score, obj)
            if score == len(expected):
                break

    return best[1] if best else None


def _build_synthesis_messages(
    scenario: str,
    fetched_regs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Construct a fresh, focused conversation for the JSON verdict synthesis turn.

    We deliberately do NOT replay the bloated tool-history. Instead we package
    the regulation text the agent fetched into a single tight context summary,
    so the model has the most room possible for emitting the JSON verdict.
    """
    sections_blob_parts: list[str] = []
    for reg in fetched_regs:
        sections_blob_parts.append(f"\n\n=== {reg['id']} — {reg['title']} ({reg['jurisdiction']}) ===")
        sections_blob_parts.append(f"Applies when: {reg.get('applies_when','')}")
        for sec in reg.get("sections", [])[:8]:   # cap sections per reg to keep context tight
            heading = sec.get("heading", "")
            text = sec.get("text", "")
            if len(text) > 900:
                text = text[:900] + "…"
            sections_blob_parts.append(f"\n[{heading}]\n{text}")
    blob = "".join(sections_blob_parts)

    user_msg = (
        "/no_think\n\n"
        f"SCENARIO:\n{scenario.strip()}\n\n"
        f"REGULATIONS YOU REVIEWED (use their actual section headings as citations):\n"
        f"{blob}\n\n"
        "Skip your reasoning trace. Emit ONLY a fenced ```json ... ``` block "
        "containing one object with these fields. Do NOT write any commentary "
        "before or after the block.\n"
        "{\n"
        '  "summary": "2-4 sentences",\n'
        '  "applicable_regulations": [{"reg_id":"REG_ID","title":"Full title","jurisdiction":"...","why_applicable":"why THIS scenario triggers it"}],\n'
        '  "requirements": [{"requirement":"imperative","citation":"REG_ID §Section","priority":"must|should|watch","rationale":"why THIS scenario triggers it"}],\n'
        '  "risk_flags": [{"flag":"...","citation":"REG_ID §Section","severity":"high|medium|low","rationale":"..."}],\n'
        '  "cross_references": [{"title":"Unified workflow name","involves":["REG_ID §Section","..."],"note":"how one workflow satisfies multiple"}],\n'
        '  "recommended_next_steps": ["..."],\n'
        '  "open_questions": ["..."]\n'
        "}\n"
        "Rules: cross_references is OPTIONAL — only include real overlaps; empty array otherwise. "
        "Use the exact reg_ids and section headings shown above. Keep summary tight."
    )

    return [
        {
            "role": "system",
            "content": (
                "You are a compliance analyst. Output ONLY a single fenced JSON block "
                "matching the schema given by the user. No preamble, no markdown report, no commentary."
            ),
        },
        {"role": "user", "content": user_msg},
    ]


def _degraded_verdict(messages: list[dict], scenario: str) -> dict[str, Any]:
    """Last-resort: synthesize a minimal verdict from the regulations the agent
    already fetched via get_regulation tool calls. Better than showing nothing."""
    fetched_ids: list[str] = []
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            if fn.get("name") == "get_regulation":
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                    rid = args.get("reg_id")
                    if rid and rid not in fetched_ids:
                        fetched_ids.append(rid)
                except json.JSONDecodeError:
                    continue

    applicable = []
    open_qs: list[str] = []
    for rid in fetched_ids:
        reg = load_regulation(rid)
        if reg is None:
            continue
        applicable.append({
            "reg_id": rid,
            "title": reg["title"],
            "jurisdiction": reg["jurisdiction"],
            "why_applicable": reg.get("applies_when") or "Flagged as potentially applicable by the agent.",
        })

    if not applicable:
        open_qs.append(
            "The agent did not finish fetching any regulations before stopping. "
            "Try re-running, or refine the scenario with more jurisdictional detail."
        )

    return {
        "summary": (
            "The agent identified candidate regulations but did not produce a fully structured verdict. "
            "This is a degraded view — the regulations below are the ones the agent pulled from the corpus, "
            "but specific requirements and risk flags were not enumerated. Re-running the analysis usually fixes this."
        ),
        "applicable_regulations": applicable,
        "requirements": [],
        "risk_flags": [],
        "cross_references": [],
        "recommended_next_steps": [
            "Click Retry analysis to attempt the run again.",
            "Add more jurisdictional detail to the scenario (e.g., where candidates live, employer headcount).",
        ],
        "open_questions": open_qs,
        "_degraded": True,
    }


# ──────────────────────────── chat helper ───────────────────────────────

def _chat(
    client: OpenAI,
    model: str,
    messages: list[dict],
    *,
    use_tools: bool = True,
    max_tokens: int = 2048,
) -> Any:
    """One chat completion call with cache + transient-error retry.

    We never pin tool_choice to a specific function — that triggers 500s on
    the Crusoe Nemotron routing. Only "auto" (with tools) or no tools at all.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if use_tools:
        kwargs["tools"] = TOOLS
        kwargs["tool_choice"] = "auto"

    payload = {**kwargs}
    cached = cache.get(payload)
    if cached is not None:
        return _CachedResponse(cached)

    import time as _time
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(**kwargs)
            try:
                cache.put(payload, resp.model_dump())
            except Exception:
                pass
            return resp
        except Exception as e:
            last_exc = e
            msg = str(e).lower()
            transient = (
                "500" in msg
                or "502" in msg
                or "503" in msg
                or "504" in msg
                or "internalservererror" in msg
                or "timeout" in msg
                or "rate limit" in msg
                or "rate_limit" in msg
            )
            if not transient or attempt == 2:
                raise
            _time.sleep(1.0 * (2 ** attempt))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM call failed after retries")


class _CachedResponse:
    """Lightweight stand-in for a chat.completions response loaded from cache."""

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self.choices = [_CachedChoice(c) for c in data.get("choices", [])]
        usage = data.get("usage") or {}
        self.usage = type("U", (), {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        })()


class _CachedChoice:
    def __init__(self, data: dict[str, Any]):
        m = data.get("message", {}) or {}
        tool_calls = m.get("tool_calls") or []
        self.message = type("M", (), {
            "role": m.get("role", "assistant"),
            "content": m.get("content"),
            "reasoning": m.get("reasoning"),
            "tool_calls": [_CachedToolCall(t) for t in tool_calls],
        })()
        self.finish_reason = data.get("finish_reason")


class _CachedToolCall:
    def __init__(self, data: dict[str, Any]):
        self.id = data.get("id", "")
        self.type = data.get("type", "function")
        fn = data.get("function") or {}
        self.function = type("F", (), {
            "name": fn.get("name", ""),
            "arguments": fn.get("arguments", "{}"),
        })()


def _serialize_tool_calls(tool_calls: Iterable[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        out.append({
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            },
        })
    return out


# ──────────────────────────── agent loop ────────────────────────────────

def run_agent(scenario: str, model: str | None = None) -> Generator[tuple[str, Any], None, None]:
    """Run the agent on a user scenario, yielding trace events as they happen."""
    model = model or DEFAULT_MODEL
    try:
        client = make_client()
    except Exception as e:
        yield ("error", str(e))
        return

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": scenario.strip()},
    ]

    total_prompt_tokens = 0
    total_completion_tokens = 0
    verdict_emitted = False

    yield ("status", "Analyzing scenario…")

    json_fallback_used = False
    tool_calls_made_count = 0  # count of assistant turns that contained tool_calls
    fetched_regs_for_synthesis: list[dict[str, Any]] = []  # full regs the agent pulled

    for step in range(MAX_LOOP_STEPS):
        # On the JSON-fallback turn we don't expose tools — the model just
        # needs to emit JSON in content. Bigger token budget for the synthesis.
        if json_fallback_used:
            use_tools = False
            # Synthesis turn: the prompt directs Nemotron to skip its reasoning
            # trace (/no_think), but if it ignores that we still want enough
            # budget for both reasoning AND a multi-section verdict object.
            max_tokens = 12000
        else:
            use_tools = True
            max_tokens = 2048

        try:
            resp = _chat(client, model, messages, use_tools=use_tools, max_tokens=max_tokens)
        except Exception as e:
            yield ("error", f"LLM call failed: {e}")
            return

        usage = getattr(resp, "usage", None)
        if usage is not None:
            total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0

        choice = resp.choices[0]
        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None) or []
        # Nemotron exposes a separate reasoning field. If content is empty,
        # search reasoning too — small models sometimes drop the final JSON
        # into the thinking trace.
        msg_content = (getattr(msg, "content", None) or "").strip()
        msg_reasoning = (getattr(msg, "reasoning", None) or "").strip()

        # Surface the model's thinking trace as a separate event so the UI
        # can show "Reasoning" as a distinct step in the timeline.
        if msg_reasoning and not json_fallback_used:
            # Trim very long reasoning to keep the trace skimmable
            reasoning_excerpt = msg_reasoning
            if len(reasoning_excerpt) > 600:
                reasoning_excerpt = reasoning_excerpt[:600].rstrip() + "…"
            yield ("thinking", reasoning_excerpt)

        # On the fallback turn, try every available channel for a JSON verdict
        # before declaring defeat.
        if json_fallback_used and not tool_calls:
            combined_search = "\n".join(filter(None, [msg_content, msg_reasoning]))
            parsed = _extract_json_verdict(combined_search)
            if parsed is not None and isinstance(parsed, dict) and parsed.get("summary"):
                yield ("verdict", parsed)
                verdict_emitted = True
                break

            # Last-resort: synthesize a degraded verdict from whatever
            # regulations the agent fetched. Better than a blank screen.
            # Surface the raw output so the user can see WHY it failed to
            # parse (truncation, prose, unexpected schema, etc.).
            raw_excerpt = msg_content or msg_reasoning or ""
            if len(raw_excerpt) > 1200:
                raw_excerpt = raw_excerpt[:1200].rstrip() + " […truncated for display]"
            if raw_excerpt:
                yield ("model_text", raw_excerpt)
            reason = "no parseable JSON in the response"
            if not msg_content and msg_reasoning:
                reason = "response stayed in the reasoning trace and no JSON content was emitted"
            elif msg_content and "{" not in msg_content:
                reason = "model wrote prose without any JSON object"
            elif msg_content and msg_content.count("{") > msg_content.count("}"):
                reason = "JSON was emitted but truncated mid-output (likely hit the token budget)"
            yield ("status", f"Falling back to a degraded summary — {reason}.")
            degraded = _degraded_verdict(messages, scenario)
            yield ("verdict", degraded)
            verdict_emitted = True
            break

        if not tool_calls:
            # If the model wrote text WITHOUT ever invoking a tool, treat it
            # as a conversational reply (triage path A from the system prompt:
            # the input was a greeting, meta-question, off-topic, or too vague).
            if tool_calls_made_count == 0 and msg_content and not json_fallback_used:
                yield ("conversational", msg_content)
                # Compute usage + stop. No verdict for non-scenarios.
                cost = (
                    total_prompt_tokens / 1_000_000 * NANO_INPUT_PER_M
                    + total_completion_tokens / 1_000_000 * NANO_OUTPUT_PER_M
                )
                yield (
                    "usage",
                    {
                        "prompt_tokens": total_prompt_tokens,
                        "completion_tokens": total_completion_tokens,
                        "cost_usd": round(cost, 6),
                        "model": model,
                    },
                )
                return

            # Otherwise: model engaged the pipeline but wrote text instead of
            # calling emit_verdict. Trigger the JSON-fallback path with a FRESH
            # focused conversation (full message history would crowd out the
            # response budget).
            if msg_content:
                yield ("model_text", msg_content)
            if not verdict_emitted and not json_fallback_used:
                if not fetched_regs_for_synthesis:
                    # Model wrote text without fetching anything — degrade now.
                    yield ("status", "Model wrote prose without fetching any regulations — falling back.")
                    yield ("verdict", _degraded_verdict(messages, scenario))
                    verdict_emitted = True
                    break
                yield ("status", "Synthesizing verdict from fetched regulations…")
                messages = _build_synthesis_messages(scenario, fetched_regs_for_synthesis)
                json_fallback_used = True
                continue
            break

        # Tool calls were made on this turn.
        if msg_content:
            yield ("model_text", msg_content)
        tool_calls_made_count += 1
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": _serialize_tool_calls(tool_calls),
        })

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            yield ("tool_call", {"id": tc.id, "name": name, "args": args})

            if name == "emit_verdict":
                verdict_emitted = True
                yield ("verdict", args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"ok": True}),
                })
                continue

            result = dispatch_tool(name, args)
            # Remember the full regulation payloads so we can rebuild a focused
            # synthesis context if the JSON-fallback path needs it.
            if name == "get_regulation" and isinstance(result, dict) and result.get("id"):
                if not any(r["id"] == result["id"] for r in fetched_regs_for_synthesis):
                    fetched_regs_for_synthesis.append({
                        "id": result["id"],
                        "title": result.get("title", result["id"]),
                        "jurisdiction": result.get("jurisdiction", ""),
                        "applies_when": result.get("applies_when", ""),
                        "sections": result.get("sections", []),
                    })
            yield (
                "tool_result",
                {
                    "id": tc.id,
                    "name": name,
                    "summary": summarize_tool_result(name, result),
                    "payload": result,
                },
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })

        if verdict_emitted:
            break

    # If we exited the loop without a verdict, try one last guaranteed
    # synthesis call before giving up to degraded mode. This covers the case
    # where the model fetched so many regulations that MAX_LOOP_STEPS ran out
    # before the fallback turn could execute.
    if not verdict_emitted and fetched_regs_for_synthesis:
        yield ("status", "Last-chance synthesis call…")
        try:
            synth_messages = _build_synthesis_messages(scenario, fetched_regs_for_synthesis)
            resp = _chat(client, model, synth_messages, use_tools=False, max_tokens=12000)
            usage = getattr(resp, "usage", None)
            if usage is not None:
                total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0
            choice = resp.choices[0]
            msg = choice.message
            msg_content = (getattr(msg, "content", None) or "").strip()
            msg_reasoning = (getattr(msg, "reasoning", None) or "").strip()
            parsed = _extract_json_verdict("\n".join(filter(None, [msg_content, msg_reasoning])))
            if parsed is not None and isinstance(parsed, dict) and parsed.get("summary"):
                yield ("verdict", parsed)
                verdict_emitted = True
            elif msg_content:
                excerpt = msg_content[:1200] + (" […truncated for display]" if len(msg_content) > 1200 else "")
                yield ("model_text", excerpt)
        except Exception as e:
            yield ("status", f"Last-chance synthesis failed: {e}")

    if not verdict_emitted:
        yield ("status", "Falling back to a degraded summary built from the fetched regulations.")
        yield ("verdict", _degraded_verdict(messages, scenario))
        verdict_emitted = True

    cost = (
        total_prompt_tokens / 1_000_000 * NANO_INPUT_PER_M
        + total_completion_tokens / 1_000_000 * NANO_OUTPUT_PER_M
    )
    yield (
        "usage",
        {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "cost_usd": round(cost, 6),
            "model": model,
        },
    )


# ──────────────────────────── CLI smoke ─────────────────────────────────

if __name__ == "__main__":
    import sys

    scenario = (
        " ".join(sys.argv[1:])
        or "We want to deploy an AI hiring tool that screens resumes for a NYC company."
    )
    for kind, payload in run_agent(scenario):
        if kind == "verdict":
            print("\n=== VERDICT ===")
            print(json.dumps(payload, indent=2))
        elif kind == "tool_call":
            print(f"[tool_call] {payload['name']}({payload['args']})")
        elif kind == "tool_result":
            print(f"[tool_result] {payload['summary']}")
        elif kind == "model_text":
            print(f"[narration] {payload}")
        elif kind == "thinking":
            print(f"[thinking] {payload[:160]}{'…' if len(payload) > 160 else ''}")
        elif kind == "conversational":
            print(f"\n=== CONVERSATIONAL REPLY ===\n{payload}\n")
        elif kind == "usage":
            print(f"[usage] {payload}")
        elif kind == "status":
            print(f"[status] {payload}")
        elif kind == "error":
            print(f"[error] {payload}", file=sys.stderr)
