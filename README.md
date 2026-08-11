# Compliance Copilot

A regulatory analysis agent for AI-and-employment scenarios. Type a business scenario in plain English; the agent decides which regulations apply, fetches the relevant sections from a local corpus, cross-references them against the facts, and returns a structured compliance plan with verifiable citations and a downloadable PDF.

Runs on NVIDIA Nemotron via Crusoe Managed Inference.

## What it does

You type:

> *We're deploying an AI resume-screening tool for a tech company headquartered in NYC. Candidates apply from across the US and occasionally from the EU.*

The agent:

1. Triages the input. Greetings or off-topic messages get a short conversational reply; the analysis pipeline only runs for real scenarios.
2. Plans which regulations from the local corpus may apply.
3. Fetches each candidate regulation via a `get_regulation` tool call.
4. Cross-references the scenario against the requirements it just read.
5. Emits a structured verdict containing:
   - Executive summary
   - Applicable regulations with jurisdictional rationale
   - Required actions tagged `must` / `should` / `watch`, each with a citation and a one-sentence rationale specific to the scenario
   - Risk flags tagged `high` / `medium` / `low`
   - Overlaps where one workflow can satisfy multiple regulations (e.g., a single candidate notification covering both NYC LL144 §3 and GDPR Art.13)
   - Recommended next steps
   - Open questions — facts that would sharpen the analysis

Every citation in the UI is a `<details>` element. Click it and the actual regulation section text expands inline.

Typical run: ~3–5 tool calls, ~20K input tokens, ~10K output tokens, ~$0.003 on Nemotron-3-Nano. Triaged-out inputs cost ~$0.0001.

## Architecture

```
┌────────────────┐    ┌──────────────────────────────────────┐    ┌──────────────────┐
│  Streamlit UI  │◄──►│  agent.py                            │◄──►│  Crusoe Cloud    │
│  (app.py)      │    │   - input triage                     │    │  Nemotron-3-Nano │
│                │    │   - tool-calling loop                │    │  (OpenAI-compat) │
│  - live trace  │    │   - JSON-fallback synthesis path     │    └──────────────────┘
│  - verdict     │    │   - degraded-mode safety net         │
│  - citations   │    │   - retry on transient 5xx           │
│  - PDF export  │    │   - disk cache (cache.py)            │
└────────────────┘    └─────────────────┬────────────────────┘
                                        │
                              ┌─────────▼──────────┐
                              │  data/*.md         │
                              │  regulation corpus │
                              └────────────────────┘
                                        ▲
                              ┌─────────┴──────────┐
                              │  export.py         │
                              │  reportlab PDF     │
                              └────────────────────┘
```

### Tools

| Tool | Purpose |
| --- | --- |
| `list_regulations()` | Returns the corpus index: id, jurisdiction, domain, applicability triggers, routing keywords. |
| `get_regulation(reg_id)` | Returns a regulation's full text broken into sections, with metadata (effective date, enforcer, penalties). |
| `emit_verdict(...)` | Final structured output. |

### Resilience

Three layers handle the cases where the LLM doesn't follow the happy path:

1. No specific-function `tool_choice` pinning. Only `"auto"` (with tools) or no tools.
2. JSON synthesis fallback. If the model writes plain text instead of calling `emit_verdict`, the agent builds a fresh, focused conversation (scenario + tight summary of fetched regulations, no bloated tool history) and asks for a fenced JSON block. A brace-balanced parser handles nested objects and arrays.
3. Degraded verdict. If JSON parsing fails too, the agent synthesizes a minimal verdict from the regulations it did fetch.

Plus transient-error retry: 3 attempts with 1s/2s exponential backoff on 5xx, timeout, and rate-limit errors.

## Corpus

Seven regulations in `data/` (markdown with YAML frontmatter):

| File | Regulation | Jurisdiction |
| --- | --- | --- |
| `nyc_ll144.md` | NYC Local Law 144 — Automated Employment Decision Tools | New York City |
| `eeoc_ai_hiring.md` | EEOC Title VII guidance on AI in hiring | US federal |
| `gdpr.md` | GDPR Art. 5, 6, 9, 13–14, 22, 35, 44–49 | EU / EEA |
| `eu_ai_act.md` | EU AI Act — prohibited + high-risk + deployer duties | EU / EEA |
| `ccpa_cpra.md` | California Consumer Privacy Act / CPRA — ADMT | California |
| `colorado_ai_act.md` | Colorado AI Act (SB 24-205) | Colorado |
| `illinois_aivi.md` | Illinois AI Video Interview Act | Illinois |
| `index.md` | Routing index consumed by `list_regulations` | — |

Adding a regulation: drop a new markdown file into `data/` with matching frontmatter, add an entry in `data/index.md`. No code change.

## UI

- Hero scenario card with Cabin typography and a focus ring on the textarea.
- Live reasoning timeline: vertical connected nodes for tool calls, tool results, and the model's thinking trace from Nemotron's `reasoning` field.
- Stats strip: Risk / Frameworks / Requirements / Citations with a colored top band per status.
- Framework cards in a 2-column grid, with a colored left band per jurisdiction.
- Action rows with priority pills, citation text, expandable source, and a one-line rationale block.
- Risk flag rows with severity pills.
- Cross-references shown as their own cards.
- PDF export (reportlab) plus a raw JSON download.

## Setup

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # paste your Crusoe key into .env
```

Confirm the API key works:

```bash
python smoke_test.py
```

Run from the CLI:

```bash
python agent.py "We want to deploy an AI hiring tool in NYC."
```

Launch the UI:

```bash
streamlit run app.py
```

## Configuration

| Env var | Default | Effect |
| --- | --- | --- |
| `CRUSOE_API_KEY` | *(required)* | Auth for the Crusoe inference endpoint. |
| `COMPLIANCE_MODEL` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Override to a larger Nemotron when you need longer context or stronger reasoning. |
| `COMPLIANCE_CACHE` | `1` | Set to `0` to disable the disk cache (`.cache/`). |
| `SUPABASE_URL` | *(optional)* | Enables private, cross-device case history. |
| `SUPABASE_ANON_KEY` | *(optional)* | Public Supabase publishable/anon key for user-scoped history. |

## Private case history

Compliance scenarios can contain sensitive business details, so history is disabled
until a Supabase project is connected. When enabled, users sign in with a one-time
email code and can only read or change their own cases; this is enforced by database
row-level security, not by the UI.

1. Create a Supabase project and run [`supabase/schema.sql`](supabase/schema.sql) in
   **SQL Editor**.
2. In **Authentication → Email Templates**, configure the sign-in email to include
   `{{ .Token }}` so the app can verify the six-digit code.
3. Add the project URL and its publishable/anon key to local `.env` or your host's
   secrets:

   ```toml
   SUPABASE_URL = "https://your-project.supabase.co"
   SUPABASE_ANON_KEY = "your-publishable-or-anon-key"
   ```

4. Redeploy. The **Cases** workspace then saves completed analyses automatically.

Never add a Supabase `service_role` or secret key to Streamlit secrets. The app uses
the public key plus the signed-in user's short-lived session, and the SQL policies
limit every query to that user.

The Streamlit theme is pinned in `.streamlit/config.toml` so the app doesn't auto-switch into dark mode based on OS preference.

## Files

```
.
├── .env                  # API key (gitignored)
├── .env.example
├── .gitignore
├── .streamlit/
│   └── config.toml       # pinned light theme + brand colors
├── README.md
├── requirements.txt
├── smoke_test.py         # confirms Crusoe API works
├── app.py                # Streamlit UI
├── agent.py              # agent loop, LLM client, tools
├── cache.py              # disk cache for LLM responses
├── export.py             # PDF generation (reportlab)
├── data/                 # 7 regulations + routing index
└── fonts/                # Cabin TTF family for the PDF
```

## Design notes

- **Why a frontmatter corpus instead of a vector DB?** The corpus is small and the routing decision is reasoning, not similarity search. Letting the model read the index and choose what to fetch produces sharper citations than top-k retrieval.
- **Why surface the reasoning trace?** Nemotron exposes its thinking content separately from the final answer. Surfacing it makes the multi-step loop legible instead of feeling like a black box.
- **Why the JSON synthesis fallback?** Small models occasionally narrate the answer instead of calling the final tool. The obvious workaround (pinning `tool_choice` to `emit_verdict`) returns empty 500s from the current Crusoe routing for this model. The fallback rebuilds a focused synthesis prompt and asks for a fenced JSON block.
- **Why input triage?** A scoping tool that runs the full pipeline on "hi" looks broken. The system prompt routes greetings, meta-questions, off-topic, and too-vague inputs to a one-call conversational reply.
- **Why inline-expandable citations?** Trustworthiness. Clicking a citation pill shows the actual section text from the corpus without leaving the page.

## Limitations

- Compact corpus. Seven regulations covers the core AI-and-employment landscape but not every adjacent law (ADA, state biometric privacy acts, sector-specific FCRA rules). Adding more is a markdown file + an index entry.
- No external authoritative source. The agent reads what's in `data/`. If a regulation is updated the corpus needs updating too. Not a real-time legal database.
- Cross-references are model-generated. Overlaps surfaced in the verdict come from the model's reasoning, not a rule engine. They should be confirmed before acting on them.
- The PDF is an informational summary, not legal advice. Every generated PDF carries this disclaimer in the footer.
