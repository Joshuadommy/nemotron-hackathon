"""Compliance Copilot — Streamlit UI.

Concept: case file → reasoning timeline → verdict dossier. User describes a
scenario; the Nemotron agent plans, fetches regulations, cross-references,
and emits a structured plan. Each citation pill expands inline to show the
actual regulation section text pulled from the local corpus.

Design: white cards on off-white canvas, Cabin typography, indigo / fawn /
dusk palette, JetBrains Mono for IDs and citations.
"""
from __future__ import annotations

import html
import json
import re
import time

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from agent import DEFAULT_MODEL, load_index, load_regulation, run_agent
from export import build_pdf
from history_store import AuthenticatedUser, HistoryStore

load_dotenv()

st.set_page_config(
    page_title="Compliance Copilot",
    page_icon="⚖",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ──────────────────────────── theme ─────────────────────────────────────

PORTFOLIO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cabin:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --fawn:        #CAB388;
  --fawn-soft:   #FBF4E6;
  --fawn-deep:   #8C7340;
  --indigo:      #1A2A59;
  --indigo-d:    #101A38;
  --indigo-soft: #E8EAF2;
  --dusk:        #42547E;
  --dusk-soft:   #ECEFF5;
  --white:       #FFFFFF;
  --off:         #F7F6F3;
  --light:       #EDEDEA;
  --line:        #E6E4DE;
  --line-2:      #EFEDE7;
  --muted:       #8A8A8A;
  --muted-2:     #B6B3AC;
  --text:        #1C1C1C;
  --text-2:      #555555;
  --danger:      #B43E3E;
  --danger-soft: #FDECEC;
  --ok:          #4F7A4A;
  --ok-soft:     #EAF1E8;
}

/* ── Streamlit chrome ──────────────────────────────────────────────── */
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stMainMenu"],
[data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"],
[data-testid="stDecoration"],
button[kind="header"],
#MainMenu, footer { display: none !important; height: 0 !important; visibility: hidden !important; }

/* Force light canvas — wins over Streamlit's theme variables. */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
.main, .main .block-container, section.main {
  background: var(--off) !important;
  color: var(--text) !important;
}

html, body, .stApp, .stMarkdown, p, div, span, label, textarea, input, button,
[class*="st-emotion-cache"] {
  font-family: 'Cabin', sans-serif !important;
}

.block-container {
  max-width: 1040px !important;
  padding: 28px 24px 64px !important;
  background: transparent !important;
}

/* Override Streamlit's CSS variables so any element using them respects our palette. */
:root, .stApp {
  --primary-color: var(--indigo) !important;
  --background-color: var(--off) !important;
  --secondary-background-color: var(--white) !important;
  --text-color: var(--text) !important;
}

/* ── Header ─────────────────────────────────────────────────────────── */
.cc-card {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 16px;
}

.cc-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 22px 28px;
  margin-bottom: 28px;
}
.cc-brand { display: flex; align-items: center; gap: 14px; }
.cc-brand-mark {
  width: 40px; height: 40px; border-radius: 11px;
  background: linear-gradient(135deg, var(--indigo) 0%, var(--dusk) 100%);
  display: flex; align-items: center; justify-content: center;
  color: var(--fawn); font-size: 20px; font-weight: 700;
  box-shadow: 0 4px 14px rgba(26, 42, 89, 0.18);
}
.cc-brand-name {
  font-size: 17px; font-weight: 600; color: var(--text);
  letter-spacing: -0.2px;
}
.cc-brand-sub {
  font-size: 11.5px; color: var(--muted); margin-top: 2px;
}

.cc-status-pill {
  display: inline-flex; align-items: center; gap: 9px;
  padding: 8px 14px;
  background: var(--indigo-soft);
  border: 1px solid rgba(26, 42, 89, 0.14);
  border-radius: 100px;
  font-size: 11.5px; font-weight: 600; letter-spacing: 0.3px;
  color: var(--indigo);
}
.cc-status-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--indigo);
  box-shadow: 0 0 10px var(--indigo);
}
.cc-status-pill.running {
  background: var(--fawn-soft);
  border-color: rgba(202, 179, 136, 0.55);
  color: var(--fawn-deep);
}
.cc-status-pill.running .cc-status-dot {
  background: var(--fawn); box-shadow: 0 0 10px var(--fawn);
  animation: ccPulse 1.3s infinite;
}
.cc-status-pill.done {
  background: var(--ok-soft);
  border-color: rgba(79, 122, 74, 0.3);
  color: var(--ok);
}
.cc-status-pill.done .cc-status-dot { background: var(--ok); box-shadow: 0 0 10px var(--ok); }
.cc-status-pill.error {
  background: var(--danger-soft);
  border-color: rgba(180, 62, 62, 0.25);
  color: var(--danger);
}
.cc-status-pill.error .cc-status-dot { background: var(--danger); box-shadow: 0 0 10px var(--danger); }
@keyframes ccPulse {
  0%   { transform: scale(1);   box-shadow: 0 0 10px var(--fawn); }
  50%  { transform: scale(1.4); box-shadow: 0 0 16px var(--fawn); }
  100% { transform: scale(1);   box-shadow: 0 0 10px var(--fawn); }
}
@keyframes ccFadeUp {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
.cc-fade { animation: ccFadeUp 0.5s ease both; }

/* ── Hero / Scenario ───────────────────────────────────────────────── */
.cc-hero {
  margin-bottom: 12px;
}
.cc-eyebrow {
  font-size: 10.5px; font-weight: 600; color: var(--muted);
  letter-spacing: 2px; text-transform: uppercase;
  margin-bottom: 10px;
}
.cc-eyebrow .accent { color: var(--fawn-deep); }
.cc-hero h1 {
  font-size: 32px; font-weight: 700; color: var(--text);
  letter-spacing: -0.6px; line-height: 1.15;
  margin: 0 0 8px;
}
.cc-hero h1 .accent { color: var(--fawn-deep); }
.cc-hero p.lead {
  font-size: 14.5px; color: var(--muted);
  line-height: 1.65; margin: 0 0 22px;
  max-width: 640px;
}

/* ── Textarea ───────────────────────────────────────────────────────
   Target Streamlit's BaseWeb wrapper directly with max specificity. */
[data-testid="stTextArea"] [data-baseweb="textarea"],
[data-testid="stTextArea"] [data-baseweb="base-input"] {
  border: 1px solid var(--line) !important;
  border-radius: 14px !important;
  background: var(--white) !important;
  transition: border-color .18s, box-shadow .18s !important;
  box-shadow: none !important;
}
[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
[data-testid="stTextArea"] [data-baseweb="base-input"]:focus-within {
  border-color: var(--indigo) !important;
  box-shadow: 0 0 0 3px rgba(26,42,89,0.08) !important;
}
[data-testid="stTextArea"] textarea {
  font-family: 'Cabin', sans-serif !important;
  font-size: 15.5px !important;
  line-height: 1.7 !important;
  border: none !important;
  background: transparent !important;
  color: var(--text) !important;
  padding: 18px 22px !important;
  resize: none !important;
  min-height: 130px !important;
  caret-color: var(--indigo) !important;
}
[data-testid="stTextArea"] textarea:focus {
  outline: none !important; box-shadow: none !important;
}
[data-testid="stTextArea"] textarea::placeholder {
  color: var(--muted-2) !important; opacity: 1 !important;
}

/* ── Buttons ───────────────────────────────────────────────────────
   Streamlit 1.57 uses [data-testid="stBaseButton-primary"] etc. */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button {
  font-family: 'Cabin', sans-serif !important;
  font-size: 13px !important; font-weight: 600 !important;
  letter-spacing: 0.2px !important;
  padding: 11px 22px !important;
  border-radius: 11px !important;
  transition: all .18s ease !important;
  box-shadow: none !important;
  min-height: 0 !important;
}
[data-testid="stButton"] button p,
[data-testid="stDownloadButton"] button p {
  font-family: 'Cabin', sans-serif !important;
  font-weight: 600 !important;
  margin: 0 !important;
}

/* Primary */
[data-testid="stBaseButton-primary"],
[data-testid="stDownloadButton"] button {
  background: var(--indigo) !important;
  border: 1px solid var(--indigo) !important;
  color: var(--white) !important;
}
[data-testid="stBaseButton-primary"] *,
[data-testid="stBaseButton-primary"] p,
[data-testid="stDownloadButton"] button *,
[data-testid="stDownloadButton"] button p {
  color: var(--white) !important;
}
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stDownloadButton"] button:hover {
  background: var(--indigo-d) !important;
  border-color: var(--indigo-d) !important;
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(26, 42, 89, 0.22) !important;
}
[data-testid="stBaseButton-primary"]:disabled {
  background: var(--muted-2) !important;
  border-color: var(--muted-2) !important;
  opacity: 0.55 !important; transform: none !important;
  cursor: not-allowed !important;
}
[data-testid="stBaseButton-primary"]:disabled * { color: var(--white) !important; }

/* Secondary */
[data-testid="stBaseButton-secondary"] {
  background: var(--white) !important;
  border: 1px solid var(--line) !important;
  color: var(--text) !important;
}
[data-testid="stBaseButton-secondary"] *,
[data-testid="stBaseButton-secondary"] p {
  color: var(--text) !important;
}
[data-testid="stBaseButton-secondary"]:hover {
  background: var(--off) !important;
  border-color: var(--indigo) !important;
}
[data-testid="stBaseButton-secondary"]:hover *,
[data-testid="stBaseButton-secondary"]:hover p {
  color: var(--indigo) !important;
}
[data-testid="stBaseButton-secondary"]:disabled {
  opacity: 0.5 !important;
  cursor: not-allowed !important;
}

/* Example chips — the columns block immediately after #cc-example-anchor.
   Use :has() (Chrome 105+, Safari 15.4+, Firefox 121+). */
[data-testid="stHorizontalBlock"]:has(button[data-testid="stBaseButton-secondary"]):has(~ * #cc-example-anchor),
div:has(> #cc-example-anchor) + div [data-testid="stBaseButton-secondary"],
div:has(> div > #cc-example-anchor) + div [data-testid="stBaseButton-secondary"] {
  border-radius: 100px !important;
  font-size: 12.5px !important;
  padding: 9px 16px !important;
  color: var(--dusk) !important;
}
div:has(> #cc-example-anchor) + div [data-testid="stBaseButton-secondary"]:hover,
div:has(> div > #cc-example-anchor) + div [data-testid="stBaseButton-secondary"]:hover {
  background: var(--fawn-soft) !important;
  border-color: var(--fawn) !important;
}
div:has(> #cc-example-anchor) + div [data-testid="stBaseButton-secondary"]:hover *,
div:has(> div > #cc-example-anchor) + div [data-testid="stBaseButton-secondary"]:hover p {
  color: var(--fawn-deep) !important;
}

/* ── Reasoning timeline ────────────────────────────────────────────── */
.cc-trace-card {
  padding: 22px 26px;
}
.cc-trace-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 18px;
}
.cc-trace-head-left { display: flex; align-items: center; gap: 12px; }
.cc-trace-head .cc-eyebrow { margin: 0; }
.cc-dots { display: inline-flex; gap: 4px; align-items: center; }
.cc-dots span {
  width: 5px; height: 5px; background: var(--fawn); border-radius: 50%;
  opacity: 0.3;
}
.cc-dots.running span:nth-child(1) { animation: ccFlow 1.4s infinite; animation-delay: 0s; }
.cc-dots.running span:nth-child(2) { animation: ccFlow 1.4s infinite; animation-delay: 0.18s; }
.cc-dots.running span:nth-child(3) { animation: ccFlow 1.4s infinite; animation-delay: 0.36s; }
.cc-dots.done span:nth-child(1) { opacity: 1; }
.cc-dots.done span:nth-child(2) { opacity: 0.7; }
.cc-dots.done span:nth-child(3) { opacity: 0.4; }
@keyframes ccFlow {
  0%, 80%, 100% { opacity: 0.25; transform: scale(1); }
  40%           { opacity: 1;    transform: scale(1.4); }
}
.cc-trace-elapsed {
  font-size: 11.5px; color: var(--muted);
  font-family: 'JetBrains Mono', monospace;
}

.cc-timeline {
  position: relative;
  padding-left: 28px;
  margin-top: 6px;
}
.cc-timeline::before {
  content: '';
  position: absolute;
  left: 9px; top: 12px; bottom: 12px;
  width: 2px;
  background: linear-gradient(to bottom, var(--line) 0%, var(--line) 95%, transparent 100%);
  border-radius: 1px;
}
.cc-tl-event { position: relative; padding: 10px 0; animation: ccFadeUp 0.4s ease both; }
.cc-tl-node {
  position: absolute;
  left: -23px; top: 14px;
  width: 12px; height: 12px;
  border-radius: 50%;
  background: var(--white);
  border: 2px solid var(--line);
  box-shadow: 0 0 0 3px var(--white);
}
.cc-tl-event.tool_call  .cc-tl-node { border-color: var(--fawn);   background: var(--fawn); }
.cc-tl-event.tool_result .cc-tl-node { border-color: var(--dusk);   background: var(--dusk); }
.cc-tl-event.model_text  .cc-tl-node { border-color: var(--indigo); background: var(--indigo); }
.cc-tl-event.status      .cc-tl-node { border-color: var(--muted-2); }
.cc-tl-event.usage       .cc-tl-node { border-color: var(--muted-2); background: var(--muted-2); }
.cc-tl-event.error       .cc-tl-node { border-color: var(--danger); background: var(--danger); }
.cc-tl-event.thinking    .cc-tl-node {
  border-color: var(--dusk);
  background: var(--dusk);
}
.cc-tl-event.is-live     .cc-tl-node { animation: ccPulse 1.2s infinite; }

.cc-tl-kind {
  font-size: 10px; font-weight: 600;
  letter-spacing: 1.5px; text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 4px;
}
.cc-tl-event.tool_call  .cc-tl-kind { color: var(--fawn-deep); }
.cc-tl-event.tool_result .cc-tl-kind { color: var(--dusk); }
.cc-tl-event.model_text  .cc-tl-kind { color: var(--indigo); }
.cc-tl-event.error       .cc-tl-kind { color: var(--danger); }
.cc-tl-event.thinking    .cc-tl-kind { color: var(--dusk); }
.cc-tl-event.thinking    .cc-tl-body { font-style: italic; color: var(--dusk); }

.cc-tl-body {
  font-size: 13.5px; line-height: 1.65; color: var(--text);
  word-wrap: break-word; overflow-wrap: anywhere;
}
.cc-tl-event.model_text .cc-tl-body {
  font-style: italic; color: var(--dusk);
}
.cc-tl-body code {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12.5px;
  background: var(--indigo-soft); color: var(--indigo);
  padding: 2px 8px; border-radius: 5px;
  font-weight: 500;
}
.cc-tl-body .args {
  display: block; margin-top: 8px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11.5px; color: var(--dusk);
  background: var(--off);
  padding: 8px 12px; border-radius: 8px;
  border-left: 2px solid var(--fawn);
  white-space: pre-wrap;
  line-height: 1.5;
}

.cc-trace-empty {
  font-family: 'Cabin', sans-serif;
  font-size: 14px; color: var(--muted);
  font-style: italic;
  padding: 6px 0 2px 28px;
  position: relative;
}
.cc-trace-empty::before {
  content: '';
  position: absolute;
  left: 5px; top: 8px;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--white);
  border: 2px solid var(--line);
}

/* ── Stats strip ───────────────────────────────────────────────────── */
.cc-stats {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  margin-bottom: 28px;
}
.cc-stat {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
}
.cc-stat::before {
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--line);
}
.cc-stat.risk-high::before    { background: var(--danger); }
.cc-stat.risk-medium::before  { background: var(--fawn); }
.cc-stat.risk-low::before     { background: var(--dusk); }
.cc-stat.risk-none::before    { background: var(--ok); }
.cc-stat.count::before        { background: var(--indigo); }
.cc-stat-label {
  font-size: 10px; font-weight: 600;
  color: var(--muted); letter-spacing: 1.5px;
  text-transform: uppercase; margin-bottom: 10px;
}
.cc-stat-value {
  font-size: 28px; font-weight: 700; color: var(--text);
  letter-spacing: -0.6px; line-height: 1;
}
.cc-stat-value.risk-high   { color: var(--danger); }
.cc-stat-value.risk-medium { color: var(--fawn-deep); }
.cc-stat-value.risk-low    { color: var(--dusk); }
.cc-stat-value.risk-none   { color: var(--ok); }
.cc-stat-sub {
  font-size: 11px; color: var(--muted); margin-top: 4px;
}

/* ── Section block ─────────────────────────────────────────────────── */
.cc-section { margin-bottom: 28px; }
.cc-section.animate-in { animation: ccFadeUp 0.5s ease both; }
.cc-eyebrow-row {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.cc-eyebrow-row .cc-eyebrow { margin: 0; }
.cc-eyebrow-count {
  font-size: 11px; color: var(--muted);
  font-family: 'JetBrains Mono', monospace;
}

/* ── Conversational reply (when input wasn't a real scenario) ──────── */
.cc-reply {
  background: var(--white);
  border: 1px solid var(--line);
  border-left: 3px solid var(--fawn);
  border-radius: 14px;
  padding: 22px 26px;
  display: grid;
  grid-template-columns: 40px 1fr;
  gap: 18px;
  align-items: start;
}
.cc-reply-avatar {
  width: 36px; height: 36px; border-radius: 10px;
  background: linear-gradient(135deg, var(--indigo) 0%, var(--dusk) 100%);
  color: var(--fawn);
  display: flex; align-items: center; justify-content: center;
  font-size: 17px; font-weight: 700;
  flex-shrink: 0;
}
.cc-reply-body {
  font-size: 15px; line-height: 1.7; color: var(--text);
}
.cc-reply-body .who {
  font-size: 10px; font-weight: 700; letter-spacing: 1.6px;
  text-transform: uppercase; color: var(--fawn-deep);
  margin-bottom: 8px; display: block;
}
.cc-reply-body p { margin: 0; }
.cc-reply-hint {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line-2);
  font-size: 12.5px; color: var(--muted);
  line-height: 1.6;
}
.cc-reply-hint b { color: var(--indigo); font-weight: 600; }

/* ── Summary card ──────────────────────────────────────────────────── */
.cc-summary {
  background: linear-gradient(135deg, var(--white) 0%, var(--off) 100%);
  border: 1px solid var(--line);
  border-left: 3px solid var(--indigo);
  border-radius: 14px;
  padding: 22px 26px;
  font-size: 15px; line-height: 1.75; color: var(--text);
}

/* ── Framework cards ───────────────────────────────────────────────── */
.cc-frame-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
}
.cc-frame {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 20px 22px 20px 26px;
  position: relative;
  transition: transform .2s, box-shadow .2s;
  overflow: hidden;
}
.cc-frame::before {
  content: '';
  position: absolute; left: 0; top: 14px; bottom: 14px;
  width: 3px;
  background: var(--fawn);
  border-radius: 0 2px 2px 0;
}
.cc-frame.jur-eu::before    { background: var(--indigo); }
.cc-frame.jur-us::before    { background: var(--dusk); }
.cc-frame.jur-state::before { background: var(--fawn); }
.cc-frame:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 22px rgba(28, 28, 28, 0.06);
}
.cc-frame-id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px; font-weight: 600;
  color: var(--indigo);
  letter-spacing: 1.1px;
  margin-bottom: 10px;
  display: inline-block;
}
.cc-frame-title {
  font-size: 15px; font-weight: 600; color: var(--text);
  line-height: 1.35; margin-bottom: 8px;
  letter-spacing: -0.1px;
}
.cc-frame-why {
  font-size: 12.5px; color: var(--text-2); line-height: 1.6;
  margin-bottom: 12px;
}
.cc-frame-jur {
  display: inline-block;
  font-size: 10px; font-weight: 600;
  color: var(--muted); letter-spacing: 1.2px;
  text-transform: uppercase;
  padding-top: 8px;
  border-top: 1px solid var(--line-2);
}

/* ── Action / risk rows ────────────────────────────────────────────── */
.cc-rows {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
}
.cc-row {
  padding: 16px 22px;
  border-bottom: 1px solid var(--line-2);
  display: flex; gap: 14px; align-items: flex-start;
}
.cc-row:last-child { border-bottom: none; }
.cc-row:hover { background: var(--off); }
.cc-row-pill { flex-shrink: 0; padding-top: 2px; }
.cc-row-main { flex: 1; min-width: 0; }
.cc-row-text {
  font-size: 14px; color: var(--text);
  line-height: 1.55; margin-bottom: 6px;
}
.cc-row-rationale {
  font-size: 12.5px; line-height: 1.6;
  color: var(--muted);
  font-style: italic;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--line-2);
}
.cc-row-rationale::before {
  content: 'WHY · ';
  font-style: normal; font-weight: 600;
  letter-spacing: 1.5px; font-size: 10px;
  color: var(--fawn-deep);
}

/* Cross-references */
.cc-xref {
  background: var(--white);
  border: 1px solid var(--line);
  border-left: 3px solid var(--dusk);
  border-radius: 14px;
  padding: 18px 22px;
  margin-bottom: 10px;
}
.cc-xref-title {
  font-size: 14px; font-weight: 600; color: var(--indigo);
  letter-spacing: -0.1px;
  margin-bottom: 8px;
}
.cc-xref-involves {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin-bottom: 10px;
}
.cc-xref-pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600;
  color: var(--dusk);
  background: var(--dusk-soft);
  padding: 4px 10px; border-radius: 6px;
}
.cc-xref-note {
  font-size: 13px; line-height: 1.6;
  color: var(--text-2);
}
.cc-pill {
  font-size: 10px; font-weight: 600;
  letter-spacing: 1px; text-transform: uppercase;
  padding: 5px 10px; border-radius: 7px;
  min-width: 78px; text-align: center;
  display: inline-block; line-height: 1;
  white-space: nowrap;
}
.cc-pill.critical { background: var(--danger-soft); color: var(--danger); }
.cc-pill.required { background: var(--fawn-soft);   color: var(--fawn-deep); }
.cc-pill.advised  { background: var(--indigo-soft); color: var(--indigo); }

/* ── Citation pill (expandable via <details>) ──────────────────────── */
.cc-cite { display: inline-block; margin-top: 2px; }
.cc-cite > summary {
  list-style: none; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600;
  color: var(--dusk);
  background: var(--dusk-soft);
  padding: 4px 10px 4px 10px;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: all .18s;
  letter-spacing: 0.02em;
}
.cc-cite > summary::-webkit-details-marker { display: none; }
.cc-cite > summary::before {
  content: '§';
  color: var(--fawn-deep); font-weight: 700;
}
.cc-cite > summary::after {
  content: '▸';
  font-size: 9px; color: var(--muted);
  transition: transform .18s;
  margin-left: 2px;
}
.cc-cite[open] > summary::after { transform: rotate(90deg); }
.cc-cite > summary:hover {
  background: var(--indigo-soft);
  border-color: rgba(26,42,89,0.18);
  color: var(--indigo);
}
.cc-cite-body {
  display: block;
  margin-top: 10px;
  background: var(--off);
  border: 1px solid var(--line);
  border-left: 3px solid var(--fawn);
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 12.5px; line-height: 1.65; color: var(--text-2);
  white-space: pre-wrap;
}
.cc-cite-body strong {
  display: block;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600;
  color: var(--indigo);
  margin-bottom: 8px; letter-spacing: 0.04em;
}
.cc-cite-missing {
  font-style: italic; color: var(--muted);
}

/* ── List card ─────────────────────────────────────────────────────── */
.cc-list-card {
  background: var(--white);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 4px 22px;
}
.cc-list { margin: 0; padding: 0; list-style: none; }
.cc-list li {
  font-size: 13.5px; color: var(--text); line-height: 1.65;
  padding: 13px 0 13px 26px; position: relative;
  border-bottom: 1px solid var(--line-2);
}
.cc-list-card li:last-child { border-bottom: none; }
.cc-list li::before {
  content: '→'; position: absolute; left: 0; top: 12px;
  color: var(--fawn-deep); font-weight: 600; font-size: 13px;
}
.cc-list.questions li::before { content: '?'; color: var(--indigo); font-weight: 700; }

/* ── Empty state ───────────────────────────────────────────────────── */
.cc-empty {
  background: var(--white);
  border: 1px dashed var(--line);
  border-radius: 14px;
  padding: 44px 28px;
  text-align: center;
  color: var(--muted);
  font-size: 13px; line-height: 1.75;
}
.cc-empty b {
  color: var(--indigo); display: block; margin-bottom: 6px;
  font-weight: 600; font-size: 15px;
  letter-spacing: -0.2px;
}

/* ── Private case history ─────────────────────────────────────────── */
.cc-workspace-bar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin: -8px 0 24px;
  padding: 10px 2px; border-bottom: 1px solid var(--line);
}
.cc-workspace-note { font-size: 12px; color: var(--muted); line-height: 1.4; }
.cc-verified {
  display: inline-flex; align-items: center; gap: 4px;
  margin-left: 7px; padding: 3px 7px; border-radius: 999px;
  background: var(--ok-soft); color: var(--ok);
  font-size: 9px; font-weight: 700; letter-spacing: .7px;
  text-transform: uppercase; vertical-align: middle;
}
.cc-case-meta { color: var(--muted); font-size: 11px; margin: -6px 0 10px; }

/* ── Responsive ────────────────────────────────────────────────────── */
@media (max-width: 760px) {
  .cc-frame-grid { grid-template-columns: 1fr; }
  .cc-stats { grid-template-columns: 1fr 1fr; }
  .cc-hero h1 { font-size: 26px; }
  .cc-row { flex-direction: column; align-items: flex-start; }
  .cc-workspace-bar { align-items: flex-start; flex-direction: column; }
}
</style>
"""

# Inject the stylesheet. Streamlit 1.57 sanitizes <style> tags inside
# st.markdown and scopes them inside st.html — neither reaches the parent
# document. We bypass both by rendering a 0-height components iframe that
# runs JS to append a <style> tag directly into window.parent.document.head.
_css_inner = PORTFOLIO_CSS
if _css_inner.strip().startswith("<style>"):
    _css_inner = _css_inner.strip()[len("<style>"):]
    if _css_inner.rstrip().endswith("</style>"):
        _css_inner = _css_inner.rstrip()[: -len("</style>")]

components.html(
    f"""
    <script>
    (function() {{
      const css = {json.dumps(_css_inner)};
      const id = 'cc-injected-styles';
      const head = window.parent.document.head;
      let el = window.parent.document.getElementById(id);
      if (!el) {{
        el = window.parent.document.createElement('style');
        el.id = id;
        head.appendChild(el);
      }}
      el.textContent = css;
    }})();
    </script>
    """,
    height=0,
)



# ──────────────────────────── state ─────────────────────────────────────

ss = st.session_state

# Widget keys are managed directly via session_state — set BEFORE the widget
# renders so the example/clear buttons can mutate them.
if "scenario_input" not in ss:
    ss.scenario_input = ""

ss.setdefault("trace", [])
ss.setdefault("verdict", None)
ss.setdefault("usage", None)
ss.setdefault("running", False)
ss.setdefault("started_at", None)
ss.setdefault("finished_at", None)
ss.setdefault("error", None)
ss.setdefault("submit_pending", False)
ss.setdefault("conversational", None)  # agent's friendly reply when the input wasn't a scenario
ss.setdefault("history_user", None)
ss.setdefault("active_case_id", None)
ss.setdefault("history_notice", None)

HISTORY_STORE = HistoryStore.from_environment()


EXAMPLES = [
    {
        "label": "Hiring AI · NYC",
        "text": "We're deploying an AI resume-screening tool for a tech company headquartered in NYC. Candidates apply from across the US and occasionally from the EU. The vendor says they bias-tested the model.",
    },
    {
        "label": "EU auto-reject",
        "text": "Our recruitment platform auto-rejects candidates who score below a threshold. We're a US-based company but we hire across Europe — roughly a third of applicants live in Germany, France, and Ireland.",
    },
    {
        "label": "Emotion video interviews",
        "text": "We're piloting a vendor that analyzes candidate emotion and tone during recorded video interviews. The pilot is for positions in Chicago, with plans to expand to Berlin next quarter.",
    },
    {
        "label": "Multi-state promo AI",
        "text": "We're rolling out an AI-driven promotion ranking system across all 50 states. Roughly 18% of employees are in California and 4% in Colorado. The system contributes one of three inputs to manager decisions.",
    },
]


# ──────────────────────────── corpus cache (for citation expansion) ─────

@st.cache_data(show_spinner=False)
def _corpus_lookup() -> dict:
    """Return {reg_id: {"title": ..., "jurisdiction": ..., "sections": [...]}}."""
    out: dict = {}
    for meta in load_index():
        reg = load_regulation(meta.id)
        if reg is None:
            continue
        out[meta.id] = {
            "title": reg["title"],
            "jurisdiction": reg["jurisdiction"],
            "sections": reg["sections"],
        }
    return out


CORPUS = _corpus_lookup()


def resolve_citation(citation: str) -> dict | None:
    """Parse 'REG_ID §Heading' and return matching section text from the corpus."""
    if not citation or not isinstance(citation, str):
        return None
    cite = citation.strip()
    m = re.match(r"^([A-Z][A-Z0-9_]+)\s*(.*)$", cite)
    if not m:
        return None
    reg_id = m.group(1).strip()
    ref = m.group(2).strip().lstrip("§").strip()
    reg = CORPUS.get(reg_id)
    if reg is None:
        return None
    if not ref:
        return {
            "reg_id": reg_id,
            "reg_title": reg["title"],
            "heading": "Overview",
            "text": reg["sections"][0]["text"] if reg["sections"] else "",
        }
    ref_low = ref.lower()
    for sec in reg["sections"]:
        h = sec["heading"].lstrip("§").strip().lower()
        if h.startswith(ref_low) or ref_low.startswith(h) or ref_low in h or h in ref_low:
            return {
                "reg_id": reg_id,
                "reg_title": reg["title"],
                "heading": sec["heading"],
                "text": sec["text"],
            }
    # No match — return the regulation header at least.
    return {
        "reg_id": reg_id,
        "reg_title": reg["title"],
        "heading": "Section not found",
        "text": "",
    }


def jurisdiction_class(jur: str) -> str:
    j = (jur or "").lower()
    if "european" in j or "eu" in j and "/eea" in j or "/eea" in j or "european union" in j:
        return "jur-eu"
    if "united states" in j or "federal" in j:
        return "jur-us"
    return "jur-state"


# ──────────────────────────── helpers ───────────────────────────────────

def _esc(x) -> str:
    return html.escape(x if isinstance(x, str) else str(x))


KIND_LABEL = {
    "status": "Status",
    "tool_call": "Tool call",
    "tool_result": "Tool result",
    "model_text": "Narration",
    "thinking": "Reasoning",
    "usage": "Usage",
    "error": "Error",
}


def render_status_pill() -> str:
    if ss.error:
        cls, text = "error", "Error · Nemotron"
    elif ss.running:
        cls, text = "running", "Analyzing · Nemotron"
    elif ss.verdict:
        cls, text = "done", "Plan ready · Nemotron · Crusoe"
    else:
        cls, text = "", "Nemotron · Crusoe"
    return (
        f'<div class="cc-status-pill {cls}">'
        f'<span class="cc-status-dot"></span>{_esc(text)}</div>'
    )


def render_header() -> str:
    return (
        '<div class="cc-card cc-header">'
        '  <div class="cc-brand">'
        '    <div class="cc-brand-mark">⚖</div>'
        '    <div>'
        '      <div class="cc-brand-name">Compliance Copilot</div>'
        '      <div class="cc-brand-sub">Regulatory analysis agent</div>'
        '    </div>'
        '  </div>'
        f'  {render_status_pill()}'
        '</div>'
    )


def _format_args(args: dict) -> str:
    if not args:
        return "{}"
    parts = []
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 100:
            v = v[:97] + "…"
        parts.append(f"  {k}: {v!r}")
    return "{\n" + ",\n".join(parts) + "\n}"


def render_event(kind: str, payload, *, live: bool = False) -> str:
    label = KIND_LABEL.get(kind, kind)
    classes = f"cc-tl-event {kind}"
    if live:
        classes += " is-live"

    if kind == "tool_call":
        name = payload.get("name", "")
        args = payload.get("args", {}) or {}
        body = f"<code>{_esc(name)}</code>"
        if args:
            body += f"<span class='args'>{_esc(_format_args(args))}</span>"
    elif kind == "tool_result":
        body = _esc(payload.get("summary", ""))
    elif kind == "model_text":
        text = payload if isinstance(payload, str) else str(payload)
        if len(text) > 480:
            text = text[:480] + "…"
        body = _esc(text)
    elif kind == "thinking":
        text = payload if isinstance(payload, str) else str(payload)
        if len(text) > 480:
            text = text[:480] + "…"
        body = _esc(text)
    elif kind == "usage":
        pt = payload.get("prompt_tokens", 0)
        ct = payload.get("completion_tokens", 0)
        cost = payload.get("cost_usd", 0.0)
        model = payload.get("model", "").split("/")[-1]
        body = (
            f"<code>{_esc(model)}</code>"
            f"<span class='args'>input  {pt:>6,} tok\n"
            f"output {ct:>6,} tok\n"
            f"cost   ${cost:.6f}</span>"
        )
    elif kind == "error":
        body = _esc(payload if isinstance(payload, str) else str(payload))
    else:
        body = _esc(payload if isinstance(payload, str) else str(payload))

    return (
        f'<div class="{classes}">'
        f'  <div class="cc-tl-node"></div>'
        f'  <div class="cc-tl-kind">{_esc(label)}</div>'
        f'  <div class="cc-tl-body">{body}</div>'
        f'</div>'
    )


def render_trace_card() -> str:
    running = ss.running
    elapsed_text = ""
    if ss.started_at:
        end = ss.finished_at or time.time()
        elapsed_text = f"{end - ss.started_at:0.1f}s"
    dots_cls = "cc-dots running" if running else "cc-dots done" if ss.trace else "cc-dots"

    if not ss.trace and not running:
        body = (
            '<div class="cc-trace-empty">'
            'No reasoning trace yet. Describe a scenario and the agent will plan, '
            'fetch regulations, and emit a structured plan — visibly, step by step.'
            '</div>'
        )
    else:
        events = []
        last_idx = len(ss.trace) - 1
        for i, (k, p) in enumerate(ss.trace):
            events.append(render_event(k, p, live=running and i == last_idx))
        if running and (not ss.trace or ss.trace[-1][0] != "tool_call"):
            events.append(
                '<div class="cc-tl-event status is-live">'
                '  <div class="cc-tl-node"></div>'
                '  <div class="cc-tl-kind">Working</div>'
                '  <div class="cc-tl-body" style="color: var(--muted); font-style: italic;">Agent is thinking…</div>'
                '</div>'
            )
        body = f'<div class="cc-timeline">{"".join(events)}</div>'

    return (
        '<div class="cc-card cc-trace-card cc-section">'
        '  <div class="cc-trace-head">'
        '    <div class="cc-trace-head-left">'
        f'      <span class="{dots_cls}"><span></span><span></span><span></span></span>'
        '      <span class="cc-eyebrow">Reasoning trace</span>'
        '    </div>'
        f'    <div class="cc-trace-elapsed">{_esc(elapsed_text)}</div>'
        '  </div>'
        f'  {body}'
        '</div>'
    )


def render_citation_pill(citation: str) -> str:
    """Expandable citation chip — clicking reveals the source section text."""
    src = resolve_citation(citation)
    if src is None or not src.get("text"):
        return (
            f'<span class="cc-cite" style="display:inline-block;">'
            f'<summary style="cursor:default;">{_esc(citation)}</summary>'
            f'</span>'
        )
    return (
        f'<details class="cc-cite">'
        f'  <summary>{_esc(citation)} <span class="cc-verified">✓ verified source</span></summary>'
        f'  <div class="cc-cite-body">'
        f'    <strong>{_esc(src["reg_title"])} — {_esc(src["heading"])}</strong>'
        f'    {_esc(src["text"])}'
        f'  </div>'
        f'</details>'
    )


def render_stats() -> str:
    v = ss.verdict or {}
    flags = v.get("risk_flags") or []
    severities = {(f.get("severity") or "").lower() for f in flags}
    if "high" in severities:
        risk, risk_cls = "High", "risk-high"
    elif "medium" in severities:
        risk, risk_cls = "Medium", "risk-medium"
    elif "low" in severities:
        risk, risk_cls = "Low", "risk-low"
    else:
        risk, risk_cls = "None", "risk-none"
    n_frames = len(v.get("applicable_regulations") or [])
    n_reqs = len(v.get("requirements") or [])
    n_cites = len({(r.get("citation") or "").strip() for r in (v.get("requirements") or []) if r.get("citation")})
    n_cites += len({(f.get("citation") or "").strip() for f in flags if f.get("citation")})

    return (
        '<div class="cc-stats cc-section animate-in">'
        f'  <div class="cc-stat {risk_cls}">'
        f'    <div class="cc-stat-label">Risk</div>'
        f'    <div class="cc-stat-value {risk_cls}">{_esc(risk)}</div>'
        f'    <div class="cc-stat-sub">{len(flags)} flag{"s" if len(flags)!=1 else ""}</div>'
        f'  </div>'
        f'  <div class="cc-stat count">'
        f'    <div class="cc-stat-label">Frameworks</div>'
        f'    <div class="cc-stat-value">{n_frames}</div>'
        f'    <div class="cc-stat-sub">applicable to scenario</div>'
        f'  </div>'
        f'  <div class="cc-stat count">'
        f'    <div class="cc-stat-label">Requirements</div>'
        f'    <div class="cc-stat-value">{n_reqs}</div>'
        f'    <div class="cc-stat-sub">must / should / watch</div>'
        f'  </div>'
        f'  <div class="cc-stat count">'
        f'    <div class="cc-stat-label">Citations</div>'
        f'    <div class="cc-stat-value">{n_cites}</div>'
        f'    <div class="cc-stat-sub">click any to expand</div>'
        f'  </div>'
        '</div>'
    )


def render_conversational() -> str:
    text = ss.conversational
    if not text:
        return ""
    return (
        '<div class="cc-section animate-in">'
        '  <div class="cc-eyebrow">Compliance Copilot</div>'
        '  <div class="cc-reply">'
        '    <div class="cc-reply-avatar">⚖</div>'
        '    <div class="cc-reply-body">'
        '      <span class="who">Reply</span>'
        f'     <p>{_esc(text)}</p>'
        '      <div class="cc-reply-hint">'
        'This didn\'t look like a compliance scenario, so the agent skipped the full analysis pipeline. '
        'Try describing a situation like: <b>"We\'re deploying an AI resume-screening tool for a tech company in NYC. Candidates apply from across the US."</b>'
        '      </div>'
        '    </div>'
        '  </div>'
        '</div>'
    )


def render_summary() -> str:
    s = (ss.verdict or {}).get("summary") or ""
    if not s:
        return ""
    return (
        '<div class="cc-section animate-in">'
        f'  <div class="cc-eyebrow">Executive summary</div>'
        f'  <div class="cc-summary">{_esc(s)}</div>'
        '</div>'
    )


def render_frameworks() -> str:
    apps = (ss.verdict or {}).get("applicable_regulations") or []
    if not apps:
        return ""
    cards = []
    for r in apps:
        jur = r.get("jurisdiction", "")
        cards.append(
            f'<div class="cc-frame {jurisdiction_class(jur)}">'
            f'  <div class="cc-frame-id">{_esc(r.get("reg_id",""))}</div>'
            f'  <div class="cc-frame-title">{_esc(r.get("title",""))}</div>'
            f'  <div class="cc-frame-why">{_esc(r.get("why_applicable",""))}</div>'
            f'  <div class="cc-frame-jur">{_esc(jur)}</div>'
            f'</div>'
        )
    return (
        '<div class="cc-section animate-in">'
        '  <div class="cc-eyebrow-row">'
        '    <div class="cc-eyebrow">Applicable frameworks</div>'
        f'    <div class="cc-eyebrow-count">{len(apps):02d}</div>'
        '  </div>'
        f'  <div class="cc-frame-grid">{"".join(cards)}</div>'
        '</div>'
    )


PRIORITY_PILL = {"must": ("critical", "Critical"), "should": ("required", "Required"), "watch": ("advised", "Advised")}
SEVERITY_PILL = {"high": ("critical", "High"), "medium": ("required", "Medium"), "low": ("advised", "Low")}


def render_requirements() -> str:
    reqs = (ss.verdict or {}).get("requirements") or []
    if not reqs:
        return ""
    rows = []
    for req in reqs:
        pr = (req.get("priority") or "watch").lower()
        cls, label = PRIORITY_PILL.get(pr, ("advised", pr.upper() or "ADVISED"))
        cite_pill = render_citation_pill(req.get("citation", ""))
        rationale_html = ""
        if req.get("rationale"):
            rationale_html = f'<div class="cc-row-rationale">{_esc(req["rationale"])}</div>'
        rows.append(
            f'<div class="cc-row">'
            f'  <div class="cc-row-pill"><span class="cc-pill {cls}">{_esc(label)}</span></div>'
            f'  <div class="cc-row-main">'
            f'    <div class="cc-row-text">{_esc(req.get("requirement",""))}</div>'
            f'    {cite_pill}'
            f'    {rationale_html}'
            f'  </div>'
            f'</div>'
        )
    return (
        '<div class="cc-section animate-in">'
        '  <div class="cc-eyebrow-row">'
        '    <div class="cc-eyebrow">Required actions</div>'
        f'    <div class="cc-eyebrow-count">{len(reqs):02d}</div>'
        '  </div>'
        f'  <div class="cc-rows">{"".join(rows)}</div>'
        '</div>'
    )


def render_risk_flags() -> str:
    flags = (ss.verdict or {}).get("risk_flags") or []
    if not flags:
        return ""
    rows = []
    for fl in flags:
        sev = (fl.get("severity") or "low").lower()
        cls, label = SEVERITY_PILL.get(sev, ("advised", sev.upper() or "LOW"))
        cite_pill = render_citation_pill(fl.get("citation", ""))
        rationale_html = ""
        if fl.get("rationale"):
            rationale_html = f'<div class="cc-row-rationale">{_esc(fl["rationale"])}</div>'
        rows.append(
            f'<div class="cc-row">'
            f'  <div class="cc-row-pill"><span class="cc-pill {cls}">{_esc(label)}</span></div>'
            f'  <div class="cc-row-main">'
            f'    <div class="cc-row-text">{_esc(fl.get("flag",""))}</div>'
            f'    {cite_pill}'
            f'    {rationale_html}'
            f'  </div>'
            f'</div>'
        )
    return (
        '<div class="cc-section animate-in">'
        '  <div class="cc-eyebrow-row">'
        '    <div class="cc-eyebrow">Risk flags</div>'
        f'    <div class="cc-eyebrow-count">{len(flags):02d}</div>'
        '  </div>'
        f'  <div class="cc-rows">{"".join(rows)}</div>'
        '</div>'
    )


def render_cross_references() -> str:
    refs = (ss.verdict or {}).get("cross_references") or []
    if not refs:
        return ""
    cards = []
    for x in refs:
        involves_html = "".join(
            f'<span class="cc-xref-pill">{_esc(p)}</span>'
            for p in (x.get("involves") or [])
        )
        cards.append(
            f'<div class="cc-xref">'
            f'  <div class="cc-xref-title">{_esc(x.get("title", "Shared workflow"))}</div>'
            f'  <div class="cc-xref-involves">{involves_html}</div>'
            f'  <div class="cc-xref-note">{_esc(x.get("note", ""))}</div>'
            f'</div>'
        )
    return (
        '<div class="cc-section animate-in">'
        '  <div class="cc-eyebrow-row">'
        '    <div class="cc-eyebrow">Overlaps & shared workflows</div>'
        f'    <div class="cc-eyebrow-count">{len(refs):02d}</div>'
        '  </div>'
        f'  {"".join(cards)}'
        '</div>'
    )


def render_next_steps() -> str:
    items = (ss.verdict or {}).get("recommended_next_steps") or []
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(x)}</li>" for x in items)
    return (
        '<div class="cc-section animate-in">'
        '  <div class="cc-eyebrow">Recommended next steps</div>'
        f'  <ul class="cc-list cc-list-card">{lis}</ul>'
        '</div>'
    )


def render_open_questions() -> str:
    items = (ss.verdict or {}).get("open_questions") or []
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(x)}</li>" for x in items)
    return (
        '<div class="cc-section animate-in">'
        '  <div class="cc-eyebrow">Open questions <span class="accent">— answer these to sharpen the analysis</span></div>'
        f'  <ul class="cc-list questions cc-list-card">{lis}</ul>'
        '</div>'
    )


# ──────────────────────────── callbacks (mutate widget state) ───────────

def _set_example(text: str) -> None:
    ss.scenario_input = text
    ss.trace = []
    ss.verdict = None
    ss.conversational = None
    ss.usage = None
    ss.error = None
    ss.active_case_id = None


def _clear_all() -> None:
    ss.scenario_input = ""
    ss.trace = []
    ss.verdict = None
    ss.conversational = None
    ss.usage = None
    ss.error = None
    ss.started_at = None
    ss.finished_at = None
    ss.active_case_id = None


def _start_run() -> None:
    text = (ss.scenario_input or "").strip()
    if not text or ss.running:
        return
    ss.trace = []
    ss.verdict = None
    ss.conversational = None
    ss.usage = None
    ss.error = None
    ss.running = True
    ss.started_at = time.time()
    ss.finished_at = None
    ss.submit_pending = True   # picked up after rerun to actually run the agent


def _history_user() -> AuthenticatedUser | None:
    data = ss.history_user
    if not isinstance(data, dict):
        return None
    try:
        return AuthenticatedUser(**data)
    except TypeError:
        return None


def _request_history_code() -> None:
    email = (ss.get("history_email") or "").strip().lower()
    if HISTORY_STORE is None:
        return
    if "@" not in email:
        ss.history_notice = "Enter a valid work email address."
        return
    try:
        HISTORY_STORE.request_email_code(email)
        ss.history_notice = "Check your inbox for the six-digit sign-in code."
        ss.history_code_requested = True
    except Exception:
        ss.history_notice = "We could not send a sign-in code. Check the Supabase configuration."


def _verify_history_code() -> None:
    email = (ss.get("history_email") or "").strip().lower()
    code = (ss.get("history_code") or "").strip()
    if HISTORY_STORE is None:
        return
    try:
        user = HISTORY_STORE.verify_email_code(email, code)
        ss.history_user = user.__dict__
        ss.history_notice = f"Signed in as {user.email}. Your cases are private."
        ss.history_code_requested = False
    except Exception:
        ss.history_notice = "That code did not work or has expired. Request a new code and try again."


def _sign_out_history() -> None:
    ss.history_user = None
    ss.active_case_id = None
    ss.history_notice = "Signed out."


def _load_case(record: dict) -> None:
    ss.active_case_id = record["id"]
    ss.scenario_input = record.get("scenario", "")
    ss.verdict = record.get("verdict")
    ss.trace = record.get("trace") or []
    ss.usage = record.get("usage")
    ss.conversational = None
    ss.error = None
    ss.running = False
    ss.history_notice = "Case restored. Edit the scenario and analyze again to update it."


def _save_current_case() -> None:
    user = _history_user()
    if HISTORY_STORE is None or user is None or not (ss.scenario_input or "").strip():
        return
    title = " ".join(ss.scenario_input.strip().split())[:90]
    if len(title) == 90:
        title = title.rstrip() + "…"
    try:
        saved = HISTORY_STORE.save_case(
            user,
            case_id=ss.active_case_id,
            title=title or "Untitled case",
            scenario=ss.scenario_input,
            verdict=ss.verdict,
            trace=ss.trace,
            usage=ss.usage,
        )
        ss.active_case_id = saved["id"]
        ss.history_notice = "Saved privately to your case history."
    except Exception:
        ss.history_notice = "Analysis finished, but the case could not be saved. Please try again."


def render_history_workspace() -> None:
    """Render account controls and a compact, private case picker."""
    st.html(
        '<div class="cc-workspace-bar">'
        '<div><div class="cc-eyebrow" style="margin:0 0 3px;">Private workspace</div>'
        '<div class="cc-workspace-note">Save cases, reopen them later, and keep each user\'s work separate.</div></div>'
        '</div>'
    )
    if HISTORY_STORE is None:
        with st.expander("Enable private case history"):
            st.info(
                "History is ready to connect. Add SUPABASE_URL and SUPABASE_ANON_KEY "
                "as hosted secrets, then run supabase/schema.sql once in the Supabase SQL editor."
            )
        return

    user = _history_user()
    with st.expander("Cases" + (f" · {user.email}" if user else " · Sign in"), expanded=False):
        if ss.history_notice:
            st.caption(ss.history_notice)
        if user is None:
            st.text_input("Email", key="history_email", placeholder="you@company.com")
            st.button("Email me a sign-in code", on_click=_request_history_code, key="history_request_code")
            if ss.get("history_code_requested"):
                st.text_input("Six-digit code", key="history_code", max_chars=6)
                st.button("Verify and open my cases", type="primary", on_click=_verify_history_code, key="history_verify_code")
            st.caption("Cases are private to the signed-in email address.")
            return

        c1, c2 = st.columns([3, 1])
        with c1:
            st.caption("Your most recently updated cases")
        with c2:
            st.button("Sign out", on_click=_sign_out_history, key="history_signout")
        try:
            cases = HISTORY_STORE.list_cases(user)
        except Exception:
            st.warning("We could not load your history. Your existing cases remain private; try signing in again.")
            return
        if not cases:
            st.caption("No saved cases yet. Completed analyses will appear here automatically.")
            return
        for record in cases:
            created = (record.get("updated_at") or "").replace("T", " ")[:16]
            left, right = st.columns([5, 1])
            with left:
                st.button(record.get("title") or "Untitled case", key=f"open_case_{record['id']}", use_container_width=True, on_click=_load_case, args=(record,))
                st.caption(f"Updated {created}")
            with right:
                if st.button("Delete", key=f"delete_case_{record['id']}", use_container_width=True):
                    try:
                        HISTORY_STORE.delete_case(user, record["id"])
                        if ss.active_case_id == record["id"]:
                            ss.active_case_id = None
                        st.rerun()
                    except Exception:
                        st.warning("Could not delete that case. Please try again.")


# ──────────────────────────── render ────────────────────────────────────

st.html(render_header())
render_history_workspace()

# Hero copy
st.html(
    '<div class="cc-hero cc-fade">'
    '  <div class="cc-eyebrow">Scenario · plain English</div>'
    '  <h1>What are you about to <span class="accent">deploy</span>?</h1>'
    '  <p class="lead">Describe a business situation involving an AI system or automated decision. '
    'The agent will figure out which AI-and-employment regulations apply, pull the relevant sections, '
    'and return a compliance plan with citations you can verify inline.</p>'
    '</div>'
)

# Scenario textarea (the widget itself is the card thanks to CSS)
st.text_area(
    label="scenario",
    label_visibility="collapsed",
    placeholder="e.g., We're deploying an AI resume-screening tool for a tech company headquartered in NYC. Candidates apply from across the US and occasionally from the EU.",
    key="scenario_input",
)

# Primary actions
ac1, ac2, _ = st.columns([1.4, 1, 4.6])
with ac1:
    st.button(
        "Analyze scenario  →",
        type="primary",
        use_container_width=True,
        disabled=ss.running,
        on_click=_start_run,
        key="btn_run",
    )
with ac2:
    st.button(
        "Clear",
        type="secondary",
        use_container_width=True,
        disabled=ss.running,
        on_click=_clear_all,
        key="btn_clear",
    )

# Example chips — wrap in a container we can target from CSS.
st.html('<div class="cc-eyebrow" style="margin-top:22px;">Try an example</div>')
st.html('<div id="cc-example-anchor" style="display:none;"></div>')
ex_cols = st.columns(len(EXAMPLES))
for col, ex in zip(ex_cols, EXAMPLES):
    with col:
        st.button(
            ex["label"],
            key=f"ex_{ex['label']}",
            use_container_width=True,
            disabled=ss.running,
            on_click=_set_example,
            args=(ex["text"],),
        )

if ss.error:
    err_low = (ss.error or "").lower()
    is_404 = "404" in err_low or "model_not_found" in err_low or "not found" in err_low
    is_auth = "401" in err_low or "unauthorized" in err_low or "invalid api key" in err_low
    if is_404:
        hint = (
            "The configured model name was rejected by the inference endpoint. "
            "Check <code>COMPLIANCE_MODEL</code> in your environment (or the default in "
            "<code>agent.py</code>) against the models the provider currently exposes."
        )
    elif is_auth:
        hint = (
            "Authentication failed. Verify <code>CRUSOE_API_KEY</code> in your <code>.env</code> "
            "file is set to a current key."
        )
    else:
        hint = (
            "The endpoint may be transiently overloaded. The agent already retried twice on this "
            "turn — click <em>Retry analysis</em> below to send the request again."
        )
    st.html(
        '<div style="margin-top:16px;padding:14px 18px;background:var(--danger-soft);'
        'border:1px solid rgba(180,62,62,0.25);border-radius:12px;color:var(--danger);'
        f'font-size:13.5px;line-height:1.5;">'
        f'<strong style="font-weight:600;">Agent error.</strong> {_esc(ss.error)}'
        f'<div style="margin-top:8px;font-size:12.5px;color:var(--text-2);">{hint}</div>'
        '</div>'
    )

    def _retry_run() -> None:
        if not (ss.scenario_input or "").strip() or ss.running:
            return
        ss.trace = []
        ss.verdict = None
        ss.usage = None
        ss.error = None
        ss.running = True
        ss.started_at = time.time()
        ss.finished_at = None
        ss.submit_pending = True

    rc1, _ = st.columns([1.4, 4.6])
    with rc1:
        st.button(
            "↻ Retry analysis",
            type="primary",
            use_container_width=True,
            disabled=ss.running,
            on_click=_retry_run,
            key="btn_retry",
        )


# Spacer before output
st.html('<div style="height:28px;"></div>')

output_slot = st.empty()


def paint() -> None:
    chunks: list[str] = [render_trace_card()]
    if ss.conversational and not ss.running:
        chunks.append(render_conversational())
    elif ss.verdict and not ss.running:
        chunks.append(render_stats())
        chunks.append(render_summary())
        chunks.append(render_frameworks())
        chunks.append(render_requirements())
        chunks.append(render_risk_flags())
        chunks.append(render_cross_references())
        chunks.append(render_next_steps())
        chunks.append(render_open_questions())
    elif not ss.trace and not ss.running:
        chunks.append(
            '<div class="cc-section">'
            '<div class="cc-empty"><b>Awaiting case file</b>'
            'Describe a scenario above and press <em>Analyze scenario →</em>. '
            'You\'ll see the reasoning trace populate live, then the verdict appear with '
            'expandable citations.'
            '</div></div>'
        )
    html_out = "".join(chunks)
    output_slot.empty()
    with output_slot.container():
        st.html(html_out)


# Run the agent if a click queued one up.
if ss.running and ss.submit_pending:
    ss.submit_pending = False
    try:
        for kind, payload in run_agent(ss.scenario_input):
            if kind == "verdict":
                ss.verdict = payload
                continue
            if kind == "conversational":
                ss.conversational = payload
                continue
            if kind == "usage":
                ss.usage = payload
            if kind == "error":
                ss.error = payload
            ss.trace.append((kind, payload))
            paint()
            time.sleep(0.02)
    except Exception as e:
        ss.error = str(e)
        ss.trace.append(("error", f"Agent crashed: {e}"))
        paint()
    finally:
        ss.running = False
        ss.finished_at = time.time()
        _save_current_case()
        st.rerun()
else:
    paint()


# Bottom actions (only after a verdict is ready)
if ss.verdict and not ss.running:
    st.html('<div style="height:14px;"></div>')
    bc1, bc2, bc3 = st.columns([1.5, 1, 1])
    with bc1:
        try:
            pdf_bytes = build_pdf(ss.scenario_input, ss.verdict, ss.usage)
        except Exception as e:
            pdf_bytes = None
            st.html(
                '<div style="padding:8px 12px;background:var(--danger-soft);'
                'border:1px solid rgba(180,62,62,0.25);border-radius:8px;color:var(--danger);'
                f'font-size:12px;">PDF generation failed: {_esc(str(e))}</div>'
            )
        if pdf_bytes is not None:
            st.download_button(
                "Export compliance plan (PDF)",
                data=pdf_bytes,
                file_name="compliance_plan.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key="btn_export_pdf",
            )
    with bc2:
        export_payload = json.dumps(
            {
                "scenario": ss.scenario_input,
                "verdict": ss.verdict,
                "usage": ss.usage,
                "model": (ss.usage or {}).get("model", DEFAULT_MODEL),
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            indent=2,
        )
        st.download_button(
            "Raw JSON",
            data=export_payload,
            file_name="compliance_plan.json",
            mime="application/json",
            type="secondary",
            use_container_width=True,
            key="btn_export_json",
        )
    with bc3:
        def _new_run() -> None:
            ss.scenario_input = ""
            ss.trace = []
            ss.verdict = None
            ss.usage = None
            ss.error = None
            ss.active_case_id = None
        st.button(
            "New scenario",
            type="secondary",
            use_container_width=True,
            on_click=_new_run,
            key="btn_new",
        )
