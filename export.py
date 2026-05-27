"""PDF export for Compliance Copilot verdicts.

Uses reportlab to build a clean memo-style PDF in the portfolio palette:
indigo / fawn / dusk on off-white. Inspired by probity's PDF layout.
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ──────────────────────────── font registration ─────────────────────────

FONTS_DIR = Path(__file__).parent / "fonts"

# Font names used throughout the PDF. When Cabin is registered we use it for
# everything; if registration fails (e.g., fonts/ is missing) we fall back to
# Helvetica + Courier so the PDF still renders.
FONT_BODY = "Helvetica"
FONT_BODY_BOLD = "Helvetica-Bold"
FONT_BODY_ITALIC = "Helvetica-Oblique"
FONT_BODY_BOLD_ITALIC = "Helvetica-BoldOblique"
FONT_MONO = "Courier"
FONT_MONO_BOLD = "Courier-Bold"

_fonts_registered = False


def _register_fonts() -> None:
    """Register Cabin (and Courier as mono) with reportlab. Idempotent.

    We extract Cabin into four static TTF files under fonts/ during setup;
    this function wires them up so reportlab can use them. If the files are
    missing for any reason, we silently fall back to Helvetica.
    """
    global _fonts_registered, FONT_BODY, FONT_BODY_BOLD, FONT_BODY_ITALIC, FONT_BODY_BOLD_ITALIC
    if _fonts_registered:
        return
    try:
        reg = FONTS_DIR / "Cabin-Regular.ttf"
        bold = FONTS_DIR / "Cabin-Bold.ttf"
        italic = FONTS_DIR / "Cabin-Italic.ttf"
        bi = FONTS_DIR / "Cabin-BoldItalic.ttf"
        if not (reg.exists() and bold.exists() and italic.exists() and bi.exists()):
            return
        pdfmetrics.registerFont(TTFont("Cabin", str(reg)))
        pdfmetrics.registerFont(TTFont("Cabin-Bold", str(bold)))
        pdfmetrics.registerFont(TTFont("Cabin-Italic", str(italic)))
        pdfmetrics.registerFont(TTFont("Cabin-BoldItalic", str(bi)))
        # Tell reportlab how to map bold/italic combinations to the right TTF
        # when a Paragraph uses <b> / <i> tags.
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily(
            "Cabin",
            normal="Cabin",
            bold="Cabin-Bold",
            italic="Cabin-Italic",
            boldItalic="Cabin-BoldItalic",
        )
        FONT_BODY = "Cabin"
        FONT_BODY_BOLD = "Cabin-Bold"
        FONT_BODY_ITALIC = "Cabin-Italic"
        FONT_BODY_BOLD_ITALIC = "Cabin-BoldItalic"
        _fonts_registered = True
    except Exception:
        # Fallbacks already set above. Don't crash PDF generation over fonts.
        pass


_register_fonts()


INDIGO = colors.HexColor("#1A2A59")
INDIGO_DEEP = colors.HexColor("#101A38")
FAWN = colors.HexColor("#CAB388")
FAWN_DEEP = colors.HexColor("#8C7340")
DUSK = colors.HexColor("#42547E")
WHITE = colors.HexColor("#FFFFFF")
OFF = colors.HexColor("#F7F6F3")
LINE = colors.HexColor("#E6E4DE")
LINE_2 = colors.HexColor("#EFEDE7")
MUTED = colors.HexColor("#8A8A8A")
TEXT = colors.HexColor("#1C1C1C")
TEXT_2 = colors.HexColor("#555555")
DANGER = colors.HexColor("#B43E3E")
DANGER_SOFT = colors.HexColor("#FDECEC")
FAWN_SOFT = colors.HexColor("#FBF4E6")
INDIGO_SOFT = colors.HexColor("#E8EAF2")


def _priority_color(priority: str) -> colors.Color:
    return {
        "must": DANGER,
        "should": FAWN_DEEP,
        "watch": INDIGO,
    }.get(priority, INDIGO)


def _severity_color(severity: str) -> colors.Color:
    return {
        "high": DANGER,
        "medium": FAWN_DEEP,
        "low": INDIGO,
    }.get(severity, INDIGO)


def _risk_color(level: str) -> colors.Color:
    return {
        "High": DANGER,
        "Medium": FAWN_DEEP,
        "Low": INDIGO,
        "None": colors.HexColor("#4F7A4A"),
    }.get(level, MUTED)


def _esc(text: Any) -> str:
    """HTML-escape for reportlab's Paragraph mini-HTML."""
    if not isinstance(text, str):
        text = str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _derive_risk(verdict: dict) -> str:
    flags = verdict.get("risk_flags") or []
    sevs = {(f.get("severity") or "").lower() for f in flags}
    if "high" in sevs:
        return "High"
    if "medium" in sevs:
        return "Medium"
    if "low" in sevs:
        return "Low"
    return "None"


def build_pdf(scenario: str, verdict: dict, usage: dict | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="Compliance Copilot — Compliance Plan",
        author="Compliance Copilot",
    )

    styles = getSampleStyleSheet()
    story: list = []

    # ── Header ───────────────────────────────────────────────────────────
    brand = ParagraphStyle(
        "Brand", parent=styles["Normal"],
        fontName=FONT_BODY_BOLD, fontSize=20, leading=24,
        textColor=INDIGO, spaceAfter=2,
    )
    sub = ParagraphStyle(
        "Sub", parent=styles["Normal"],
        fontName=FONT_BODY, fontSize=10, leading=13,
        textColor=MUTED, spaceAfter=18,
    )
    story.append(Paragraph("Compliance Copilot", brand))
    story.append(Paragraph(
        f"Compliance plan · Generated {datetime.now().strftime('%B %d, %Y · %I:%M %p')}",
        sub,
    ))

    # ── Scenario ─────────────────────────────────────────────────────────
    eyebrow = ParagraphStyle(
        "Eyebrow", parent=styles["Normal"],
        fontName=FONT_BODY_BOLD, fontSize=8, leading=10,
        textColor=MUTED, spaceAfter=6,
    )
    body = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontName=FONT_BODY, fontSize=11, leading=16,
        textColor=TEXT, spaceAfter=18,
    )
    story.append(Paragraph("SCENARIO", eyebrow))
    story.append(Paragraph(_esc(scenario), body))

    # ── Summary band ─────────────────────────────────────────────────────
    if verdict.get("summary"):
        story.append(Paragraph("EXECUTIVE SUMMARY", eyebrow))
        summary_style = ParagraphStyle(
            "SummaryBody", parent=body,
            backColor=OFF, borderColor=INDIGO, borderWidth=0,
            leftIndent=12, rightIndent=12,
            spaceBefore=2, spaceAfter=4,
            borderPadding=14,
        )
        story.append(Paragraph(_esc(verdict["summary"]), summary_style))
        story.append(Spacer(1, 16))

    # ── Metric tiles ─────────────────────────────────────────────────────
    risk = _derive_risk(verdict)
    n_frames = len(verdict.get("applicable_regulations") or [])
    reqs = verdict.get("requirements") or []
    flags = verdict.get("risk_flags") or []
    n_reqs = len(reqs)
    n_citations = len({(r.get("citation") or "").strip() for r in reqs + flags if r.get("citation")})

    metric_label = ParagraphStyle(
        "MetricLabel", parent=styles["Normal"],
        fontName=FONT_BODY_BOLD, fontSize=7, leading=9,
        textColor=MUTED, alignment=TA_CENTER,
    )
    metric_value = ParagraphStyle(
        "MetricValue", parent=styles["Normal"],
        fontName=FONT_BODY_BOLD, fontSize=22, leading=26,
        textColor=TEXT, alignment=TA_CENTER,
    )
    risk_value_style = ParagraphStyle(
        "RiskValue", parent=metric_value, textColor=_risk_color(risk),
    )

    metric_table = Table([
        [
            Paragraph("RISK", metric_label),
            Paragraph("FRAMEWORKS", metric_label),
            Paragraph("REQUIREMENTS", metric_label),
            Paragraph("CITATIONS", metric_label),
        ],
        [
            Paragraph(risk, risk_value_style),
            Paragraph(str(n_frames), metric_value),
            Paragraph(str(n_reqs), metric_value),
            Paragraph(str(n_citations), metric_value),
        ],
    ], colWidths=[1.65 * inch] * 4)
    metric_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, 0), 1.5, FAWN),
    ]))
    story.append(metric_table)
    story.append(Spacer(1, 22))

    # ── Applicable frameworks ────────────────────────────────────────────
    apps = verdict.get("applicable_regulations") or []
    if apps:
        story.append(Paragraph("APPLICABLE FRAMEWORKS", eyebrow))
        fw_name = ParagraphStyle(
            "FwName", parent=styles["Normal"],
            fontName=FONT_BODY_BOLD, fontSize=11, leading=14,
            textColor=TEXT, spaceAfter=3,
        )
        fw_id = ParagraphStyle(
            "FwId", parent=styles["Normal"],
            fontName=FONT_MONO_BOLD, fontSize=8, leading=10,
            textColor=INDIGO,
        )
        fw_jur = ParagraphStyle(
            "FwJur", parent=styles["Normal"],
            fontName=FONT_BODY, fontSize=8, leading=10,
            textColor=MUTED,
        )
        fw_why = ParagraphStyle(
            "FwWhy", parent=styles["Normal"],
            fontName=FONT_BODY, fontSize=9.5, leading=13,
            textColor=TEXT_2, spaceBefore=4,
        )
        rows: list = []
        for r in apps:
            left_cell = [
                Paragraph(_esc(r.get("reg_id", "")), fw_id),
                Spacer(1, 4),
                Paragraph(_esc(r.get("jurisdiction", "")), fw_jur),
            ]
            right_cell = [
                Paragraph(_esc(r.get("title", "")), fw_name),
                Paragraph(_esc(r.get("why_applicable", "")), fw_why),
            ]
            rows.append([left_cell, right_cell])
        fw_table = Table(rows, colWidths=[1.7 * inch, 4.9 * inch])
        fw_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(fw_table)
        story.append(Spacer(1, 22))

    # ── Required actions ─────────────────────────────────────────────────
    if reqs:
        story.append(Paragraph(f"REQUIRED ACTIONS · {len(reqs)} ITEMS", eyebrow))
        title_style = ParagraphStyle(
            "ActionTitle", parent=styles["Normal"],
            fontName=FONT_BODY_BOLD, fontSize=10.5, leading=14,
            textColor=TEXT, spaceAfter=3,
        )
        cite_style = ParagraphStyle(
            "Cite", parent=styles["Normal"],
            fontName=FONT_MONO, fontSize=8.5, leading=11,
            textColor=DUSK,
        )
        rationale_style = ParagraphStyle(
            "Rationale", parent=styles["Normal"],
            fontName=FONT_BODY_ITALIC, fontSize=9, leading=12,
            textColor=MUTED, spaceBefore=3,
        )
        for r in reqs:
            pr = (r.get("priority") or "watch").lower()
            label = {"must": "CRITICAL", "should": "REQUIRED", "watch": "ADVISED"}.get(pr, pr.upper())
            color = _priority_color(pr)
            pill_style = ParagraphStyle(
                "Pill", parent=styles["Normal"],
                fontName=FONT_BODY_BOLD, fontSize=7, leading=9,
                textColor=color, alignment=TA_CENTER,
            )
            pill = Table([[Paragraph(label, pill_style)]],
                         colWidths=[0.75 * inch], rowHeights=[16])
            pill.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.6, color),
            ]))

            right: list = [
                Paragraph(_esc(r.get("requirement", "")), title_style),
                Paragraph(_esc(r.get("citation", "")), cite_style),
            ]
            if r.get("rationale"):
                right.append(Paragraph(_esc(r["rationale"]), rationale_style))

            row = Table([[pill, right]], colWidths=[0.95 * inch, 5.65 * inch])
            row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE_2),
            ]))
            story.append(KeepTogether(row))
        story.append(Spacer(1, 18))

    # ── Risk flags ───────────────────────────────────────────────────────
    if flags:
        story.append(Paragraph(f"RISK FLAGS · {len(flags)} ITEMS", eyebrow))
        flag_style = ParagraphStyle(
            "FlagText", parent=styles["Normal"],
            fontName=FONT_BODY_BOLD, fontSize=10.5, leading=14,
            textColor=TEXT, spaceAfter=3,
        )
        cite_style = ParagraphStyle(
            "Cite", parent=styles["Normal"],
            fontName=FONT_MONO, fontSize=8.5, leading=11,
            textColor=DUSK,
        )
        rationale_style = ParagraphStyle(
            "Rationale", parent=styles["Normal"],
            fontName=FONT_BODY_ITALIC, fontSize=9, leading=12,
            textColor=MUTED, spaceBefore=3,
        )
        for f in flags:
            sev = (f.get("severity") or "low").lower()
            label = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW"}.get(sev, sev.upper())
            color = _severity_color(sev)
            pill_style = ParagraphStyle(
                "SevPill", parent=styles["Normal"],
                fontName=FONT_BODY_BOLD, fontSize=7, leading=9,
                textColor=color, alignment=TA_CENTER,
            )
            pill = Table([[Paragraph(label, pill_style)]],
                         colWidths=[0.75 * inch], rowHeights=[16])
            pill.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.6, color),
            ]))

            right_cells: list = [
                Paragraph(_esc(f.get("flag", "")), flag_style),
                Paragraph(_esc(f.get("citation", "")), cite_style),
            ]
            if f.get("rationale"):
                right_cells.append(Paragraph(_esc(f["rationale"]), rationale_style))

            row = Table([[pill, right_cells]], colWidths=[0.95 * inch, 5.65 * inch])
            row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE_2),
            ]))
            story.append(KeepTogether(row))
        story.append(Spacer(1, 18))

    # ── Cross-references ─────────────────────────────────────────────────
    cross = verdict.get("cross_references") or []
    if cross:
        story.append(Paragraph(f"OVERLAPS & SHARED WORKFLOWS · {len(cross)}", eyebrow))
        title_style = ParagraphStyle(
            "XRefTitle", parent=styles["Normal"],
            fontName=FONT_BODY_BOLD, fontSize=11, leading=14,
            textColor=INDIGO, spaceAfter=4,
        )
        involves_style = ParagraphStyle(
            "XRefInvolves", parent=styles["Normal"],
            fontName=FONT_MONO, fontSize=8.5, leading=11,
            textColor=DUSK, spaceAfter=4,
        )
        note_style = ParagraphStyle(
            "XRefNote", parent=styles["Normal"],
            fontName=FONT_BODY, fontSize=10, leading=13.5,
            textColor=TEXT_2, spaceAfter=10,
        )
        for c in cross:
            story.append(Paragraph(_esc(c.get("title", "Shared workflow")), title_style))
            inv = " · ".join(_esc(x) for x in (c.get("involves") or []))
            if inv:
                story.append(Paragraph(inv, involves_style))
            if c.get("note"):
                story.append(Paragraph(_esc(c["note"]), note_style))
        story.append(Spacer(1, 8))

    # ── Next steps + open questions ──────────────────────────────────────
    nxt = verdict.get("recommended_next_steps") or []
    if nxt:
        story.append(Paragraph("RECOMMENDED NEXT STEPS", eyebrow))
        for x in nxt:
            story.append(Paragraph(f"<font color='#8C7340'>→</font> {_esc(x)}", body))
        story.append(Spacer(1, 12))

    opens = verdict.get("open_questions") or []
    if opens:
        story.append(Paragraph("OPEN QUESTIONS", eyebrow))
        for x in opens:
            story.append(Paragraph(f"<font color='#1A2A59'><b>?</b></font> {_esc(x)}", body))
        story.append(Spacer(1, 12))

    # ── Footer ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 14))
    footer = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontName=FONT_BODY, fontSize=8, leading=11,
        textColor=MUTED, alignment=TA_CENTER,
    )
    model = (usage or {}).get("model", "NVIDIA Nemotron")
    cost = (usage or {}).get("cost_usd")
    cost_line = f" · ${cost:.4f} inference cost" if cost is not None else ""
    story.append(Paragraph(
        f"Generated by Compliance Copilot · {_esc(model)} via Crusoe Managed Inference{cost_line}",
        footer,
    ))
    story.append(Paragraph(
        "This document is an informational compliance summary and does not constitute legal advice.",
        footer,
    ))

    doc.build(story)
    return buf.getvalue()
