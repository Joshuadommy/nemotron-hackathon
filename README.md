# Compliance Copilot

> *"Does this scenario violate regulation X?"*

A regulatory-compliance agent built on **NVIDIA Nemotron** (served via **Crusoe Managed Inference**) that takes a plain-English business scenario, decides which AI-and-employment regulations apply, fetches the relevant sections, cross-references them against the facts, and returns a structured compliance plan with verifiable citations and a downloadable PDF.

Built for the DevNetwork AI + ML Hackathon · Crusoe Nemotron Agent Challenge.

---

## What it does

Type a scenario in plain English:

> *"We're deploying an AI resume-screening tool for a tech company headquartered in NYC. Candidates apply from across the US and occasionally from the EU."*

The agent:

1. **Triages the input.** If you say "hi" or ask an off-topic question, the agent replies conversationally and skips the pipeline — no fake analysis, no wasted spend.
2. **Plans.** Decides which of seven regulations to pull from the local corpus.
3. **Fetches** each candidate regulation via the `get_regulation` tool — visible live in the reasoning timeline so judges see real retrieval, not vibes.
4. **Cross-references** the scenario against the requirements it just read.
5. **Emits a structured verdict**:
   - Executive summary
   - Applicable regulations with jurisdictional rationale
   - Required actions tagged `must` / `should` / `watch`, each with a citation and a one-sentence **why** (rationale specific to *this* scenario, not generic regulation text)
   - Risk flags tagged `high` / `medium` / `low`, also with rationale
   - **Overlaps & shared workflows** — calls out where a single workflow (e.g., one candidate notification) satisfies multiple regulations (NYC LL144 §3 + GDPR Art.13)
   - Recommended next steps
   - Open questions — facts that would sharpen the analysis

Every citation pill in the UI is a `<details>` element. Click it and the actual regulation section text expands inline, pulled from the corpus.

Typical full run: ~3-5 tool calls, ~20K input tokens, ~10K output tokens, **~$0.003–$0.005** on Nemotron-3-Nano. Triaged-out inputs (greetings, off-topic): **~$0.0001**.

---

## Architecture

```
┌────────────────┐    ┌──────────────────────────────────────┐    ┌──────────────────┐
│  Streamlit UI  │◄──►│  agent.py                            │◄──►│  Crusoe Cloud    │
│  (app.py)      │    │   ── input triage                    │    │  Nemotron-3-Nano │
│                │    │   ── tool-calling loop               │    │  (OpenAI-compat) │
│  ▸ live trace  │    │   ── JSON-fallback synthesis path    │    └──────────────────┘
│  ▸ verdict     │    │   ── degraded-mode safety net        │
│  ▸ citations   │    │   ── retry on transient 5xx          │
│  ▸ PDF export  │    │   ── disk cache (cache.py)           │
└────────────────┘    └─────────────────┬────────────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │  data/*.md         │
                              │  (regulation       │
                              │   corpus with      │
                              │   frontmatter)     │
                              └────────────────────┘
                                        ▲
                              ┌─────────┴──────────┐
                              │  export.py         │
                              │  (reportlab PDF)   │
                              └────────────────────┘
```

### Tools the agent calls

| Tool | Purpose |
| --- | --- |
| `list_regulations()` | Returns the corpus index: id, jurisdiction, domain, applicability triggers, routing keywords. |
| `get_regulation(reg_id)` | Returns a regulation's full text broken into sections, with metadata (effective date, enforcer, penalties). |
| `emit_verdict(...)` | Final structured output. Required final call. |

### Resilience layers

The Crusoe Nemotron endpoint returns 500s when `tool_choice` is pinned to a specific function. Production-grade workaround in three layers:

1. **Never pin tool_choice.** Only `"auto"` (with tools) or no tools.
2. **JSON synthesis fallback.** If the model writes plain text instead of calling `emit_verdict`, the agent builds a *fresh, focused* conversation containing the scenario + a tight summary of the regulations it fetched (not the bloated history) and asks for a fenced JSON block. Brace-balanced parser handles nested objects and arrays.
3. **Degraded verdict.** If JSON parsing fails too, the agent synthesizes a minimal verdict from the regulations it *did* fetch (extracted from the tool-call history). Better than a blank screen.

Plus transient-error retry: 3 attempts with 1s/2s exponential backoff on 5xx, timeout, and rate-limit errors.

---

## Corpus

Seven regulations in `data/` (markdown with YAML frontmatter):

| File | Regulation | Jurisdiction |
| --- | --- | --- |
| `nyc_ll144.md` | NYC Local Law 144 — Automated Employment Decision Tools | New York City |
| `eeoc_ai_hiring.md` | EEOC Title VII guidance on AI in hiring | US Federal |
| `gdpr.md` | GDPR Art. 5, 6, 9, 13–14, 22, 35, 44–49 | EU / EEA |
| `eu_ai_act.md` | EU AI Act — prohibited + high-risk + deployer duties | EU / EEA |
| `ccpa_cpra.md` | California Consumer Privacy Act / CPRA — ADMT | California |
| `colorado_ai_act.md` | Colorado AI Act (SB 24-205) | Colorado |
| `illinois_aivi.md` | Illinois AI Video Interview Act | Illinois |
| `index.md` | Routing index consumed by `list_regulations` | — |

Extending the corpus: drop a new `*.md` file into `data/` matching the existing frontmatter shape, add an entry in `data/index.md`. Zero code change.

---

## UI features

- **Hero scenario card** — Cabin typography, indigo / fawn / dusk palette, focus ring on textarea, accent-fawn deploy verb.
- **Live reasoning timeline** — vertical connected nodes; tool calls render with monospace function names and indented args; thinking trace from Nemotron's `reasoning` field surfaces as italic dusk-colored nodes so judges see the agent *think*, not just act.
- **Phase dot animation** — three fawn dots cascade while running, settle into static dots when done, with elapsed time in mono on the right.
- **Stats strip** — Risk / Frameworks / Requirements / Citations cards with a colored top band per status.
- **Framework cards** — 2-column grid, colored left band per jurisdiction (indigo = EU, dusk = US federal, fawn = state).
- **Action rows** — priority pills (`CRITICAL` / `REQUIRED` / `ADVISED`) on the left, action text in the middle, expandable citation pill, and a "WHY · " rationale block below — explaining why *this* scenario triggers the requirement.
- **Risk flag rows** — same layout with `HIGH` / `MEDIUM` / `LOW` severity pills.
- **Cross-references** — distinct card with the unified workflow title, list of citations it satisfies as mono pills, and an explanation note.
- **Conversational replies** — when the input wasn't a scenario, a friendly bubble with the brand-mark avatar invites a real one. No fake verdict.
- **Export** — primary PDF download (reportlab, memo-style with the same palette), secondary raw-JSON download for programmatic use.

---

## Setup

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # paste your Crusoe key into .env
```

Smoke-test that Crusoe + the key work:

```bash
venv/bin/python smoke_test.py
```

Run the agent from the CLI:

```bash
venv/bin/python agent.py "We want to deploy an AI hiring tool in NYC."
```

Launch the UI:

```bash
venv/bin/streamlit run app.py
```

---

## Configuration

| Env var | Default | Effect |
| --- | --- | --- |
| `CRUSOE_API_KEY` | *(required)* | Auth for the Crusoe inference endpoint. |
| `COMPLIANCE_MODEL` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Override to a larger Nemotron when you need longer context or stronger reasoning. |
| `COMPLIANCE_CACHE` | `1` | Set to `0` to disable the disk cache (`.cache/`). |

The Streamlit theme is pinned in `.streamlit/config.toml` so the app never auto-switches into dark mode based on OS preference — judges always see the designed palette.

---

## Files

```
nemotron-hackathon/
├── .env                  # your API key (gitignored)
├── .env.example
├── .gitignore
├── .streamlit/
│   └── config.toml       # pinned light theme + brand colors
├── README.md
├── requirements.txt
├── smoke_test.py         # confirms Crusoe API works
├── app.py                # Streamlit UI
├── agent.py              # agent loop + LLM client + tools
├── cache.py              # disk cache for LLM responses
├── export.py             # PDF generation (reportlab)
└── data/                 # 7 regulations + routing index
```

---

## Design notes

- **Why a frontmatter corpus instead of a vector DB?** The corpus is small (7 regulations) and the routing decision is a reasoning task, not a similarity-search task. Letting the model read the index and choose what to fetch produces sharper citations than top-k retrieval would. Swap in a retriever later if the corpus grows past Nemotron's context budget.
- **Why surface Nemotron's reasoning trace?** The Crusoe challenge asks for an **agent**, not a chatbot. Nemotron exposes its thinking trace separately from the final answer — surfacing it as a visible timeline event makes the agentic loop legible. Judges see the model decide, fetch, reconsider, then emit.
- **Why the JSON synthesis fallback?** Small models occasionally narrate the answer in markdown instead of calling the final tool. The first instinct (pin `tool_choice` to `emit_verdict`) crashes the Crusoe routing with empty 500s. Instead, the agent rebuilds a focused synthesis prompt (scenario + tight regulation summary, no tool history) and asks for a fenced JSON block. Brace-balanced parser, scored by completeness.
- **Why input triage?** A compliance agent shouldn't engage seven LLM calls and $0.004 of spend on "hi". The system prompt routes greetings, meta-questions, off-topic, and too-vague inputs to a conversational reply in a single $0.0001 call.
- **Why an inline-expandable citation?** Trustworthiness. Every citation pill is a `<details>` element. Clicking it shows the actual section text the model was looking at — verifying the claim takes zero context-switches.

---

## Limitations & honest disclosure

- **Compact corpus.** Seven regulations covers the core AI-and-employment landscape but not every adjacent law (e.g., ADA, state biometric privacy acts, sector-specific FCRA rules). Adding more is a markdown file + an index entry — no code change.
- **No external authoritative source.** The agent reads what's in `data/`. If a regulation is updated, the corpus needs updating. Not a real-time legal database.
- **Cross-references are model-generated.** Overlaps surfaced in the verdict come from Nemotron's reasoning, not a rule engine. They're typically accurate but should be confirmed.
- **PDF is a summary, not legal advice.** Footer of every generated PDF says so.
- **Hackathon-scale design.** Production deployment would want: model fallback (e.g., AI Gateway routing Nemotron → Llama 3.3 70B on error), per-user usage tracking, persistent run history, evaluation harness against known compliance scenarios, an admin view of the corpus, and a real legal review of the corpus text itself.

---

## Demo flow (90 seconds)

1. **Open the page** — judges see the brand mark, status pill (`● Nemotron · Crusoe`), and hero typography.
2. **Type "hi"** — agent replies conversationally in one short paragraph. No fake analysis. Costs $0.0001. Shows the agent is *smart* about what to engage on.
3. **Pick an example chip** (e.g., "Hiring AI · NYC") — scenario fills in, click Analyze.
4. **Reasoning timeline streams** — fawn dots cascade, tool call nodes appear (`list_regulations`, then `get_regulation(NYC_LL144)`, then more), thinking-trace excerpts from Nemotron's `reasoning` field show what the model is considering.
5. **Verdict materializes** — stats strip lights up the Risk tile (`High` in red), framework cards fade in with colored left bands, required-actions rows with priority pills and "WHY · " rationale, risk flags, and a cross-reference card calling out the shared workflow opportunity.
6. **Click a citation pill** — actual NYC LL144 §2 text expands inline. No new page, no rerun.
7. **Click "Export compliance plan (PDF)"** — downloadable memo with the same palette, all sections, footer disclosing this is not legal advice.

The whole flow runs in ~25 seconds end-to-end, with full streaming.
