# LICENSE HEADER MANAGED BY add-license-header
#
# BSD 3-Clause License
#
# Copyright (c) 2026, Martin Vesterlund
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""Markdown report generation and pandoc-backed rendering helpers."""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from io import BytesIO
from urllib.parse import urlparse
from xml.sax.saxutils import escape as xml_escape

from src.logging_utils import get_logger
from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn
from src.schemas.debrief_response import DebriefResponse


class ReportRenderingError(RuntimeError):
    """Raised when pandoc is missing or report conversion fails."""


logger = get_logger(__name__)


_INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)\s]+(?:\s+\"[^\"]*\")?)\)")
_STRONG_ASTERISK_PATTERN = re.compile(r"\*\*([^*]+)\*\*")
_STRONG_UNDERSCORE_PATTERN = re.compile(r"__([^_]+)__")
_EM_ASTERISK_PATTERN = re.compile(r"(^|[\s(])\*([^*]+)\*(?=[\s).,!?]|$)")
_EM_UNDERSCORE_PATTERN = re.compile(r"(^|[\s(])_([^_]+)_(?=[\s).,!?]|$)")
_STRIKE_PATTERN = re.compile(r"~~([^~]+)~~")
_PAGE_BREAK_PATTERN = re.compile(r"(?m)^---\s*$")
_PANDOC_PDF_ENGINES = [
    "pdflatex",
    "weasyprint",
    "wkhtmltopdf",
    "prince",
    "tectonic",
    "xelatex",
    "lualatex",
]
_LATEX_PANDOC_PDF_ENGINES = {"pdflatex", "tectonic", "xelatex", "lualatex"}


def _escape_markdown_text(value: str) -> str:
    return str(value).replace("\\", "\\\\")


def _as_bullet_lines(items: list[str], fallback: str) -> list[str]:
    if not items:
        return [fallback]
    return [f"- {_escape_markdown_text(item)}" for item in items]


def _sanitize_heading_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def _escape_html(value: str) -> str:
    return html.escape(str(value), quote=True).replace("'", "&#39;")


def _escape_html_attribute(value: str) -> str:
    return _escape_html(value).replace("`", "&#96;")


def _sanitize_link_url(raw_url: str) -> str | None:
    trimmed = str(raw_url or "").strip()
    if not trimmed:
        return None

    if trimmed.startswith(("/", "./", "../", "#")):
        return trimmed

    parsed = urlparse(trimmed)
    if parsed.scheme in {"http", "https", "mailto"}:
        return trimmed

    return None


def _render_inline_markdown(text: str) -> str:
    code_segments: list[str] = []

    def replace_code(match: re.Match[str]) -> str:
        placeholder = f"__CODE_SEGMENT_{len(code_segments)}__"
        code_segments.append(f"<code>{_escape_html(match.group(1))}</code>")
        return placeholder

    with_code_placeholders = _INLINE_CODE_PATTERN.sub(replace_code, str(text))
    rendered = _escape_html(with_code_placeholders)

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        raw_target = match.group(2).split(' "', 1)[0]
        href = _sanitize_link_url(raw_target)
        if not href:
            return _escape_html(label)
        return (
            f'<a href="{_escape_html_attribute(href)}" target="_blank" '
            f'rel="noreferrer">{_escape_html(label)}</a>'
        )

    rendered = _LINK_PATTERN.sub(replace_link, rendered)
    rendered = _STRONG_ASTERISK_PATTERN.sub(r"<strong>\1</strong>", rendered)
    rendered = _STRONG_UNDERSCORE_PATTERN.sub(r"<strong>\1</strong>", rendered)
    rendered = _EM_ASTERISK_PATTERN.sub(r"\1<em>\2</em>", rendered)
    rendered = _EM_UNDERSCORE_PATTERN.sub(r"\1<em>\2</em>", rendered)
    rendered = _STRIKE_PATTERN.sub(r"<del>\1</del>", rendered)

    for index, segment in enumerate(code_segments):
        rendered = rendered.replace(f"__CODE_SEGMENT_{index}__", segment)

    return rendered


def _render_markdown_fragment(markdown: str) -> str:
    normalized = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    html_parts: list[str] = []
    paragraph_lines: list[str] = []
    list_type: str | None = None
    list_items: list[list[str]] = []
    quote_lines: list[str] = []
    in_code_block = False
    code_language = ""
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        html_parts.append(
            "<p>"
            + "<br />".join(_render_inline_markdown(line) for line in paragraph_lines)
            + "</p>"
        )
        paragraph_lines = []

    def flush_list() -> None:
        nonlocal list_type, list_items
        if not list_type or not list_items:
            list_type = None
            list_items = []
            return

        tag_name = "ol" if list_type == "ordered" else "ul"
        items_html = "".join(
            "<li>"
            + "<br />".join(_render_inline_markdown(line) for line in item)
            + "</li>"
            for item in list_items
        )
        html_parts.append(f"<{tag_name}>{items_html}</{tag_name}>")
        list_type = None
        list_items = []

    def flush_quote() -> None:
        nonlocal quote_lines
        if not quote_lines:
            return
        html_parts.append(
            f"<blockquote>{_render_markdown_fragment(chr(10).join(quote_lines))}</blockquote>"
        )
        quote_lines = []

    def flush_code_block() -> None:
        nonlocal in_code_block, code_language, code_lines
        if not in_code_block:
            return
        language_class = (
            f' class="language-{_escape_html_attribute(code_language)}"'
            if code_language
            else ""
        )
        html_parts.append(
            f"<pre><code{language_class}>{_escape_html(chr(10).join(code_lines))}</code></pre>"
        )
        in_code_block = False
        code_language = ""
        code_lines = []

    def flush_open_blocks() -> None:
        flush_paragraph()
        flush_list()
        flush_quote()

    for line in lines:
        trimmed = line.strip()

        if in_code_block:
            if trimmed.startswith("```"):
                flush_code_block()
            else:
                code_lines.append(line)
            continue

        code_fence_match = re.match(r"^```(\S+)?\s*$", line)
        if code_fence_match:
            flush_open_blocks()
            in_code_block = True
            code_language = code_fence_match.group(1) or ""
            continue

        if not trimmed:
            flush_open_blocks()
            continue

        quote_match = re.match(r"^>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            flush_list()
            quote_lines.append(quote_match.group(1))
            continue
        flush_quote()

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            flush_open_blocks()
            level = len(heading_match.group(1))
            html_parts.append(
                f"<h{level}>{_render_inline_markdown(heading_match.group(2))}</h{level}>"
            )
            continue

        if re.match(r"^([-*_]\s*){3,}$", trimmed):
            flush_open_blocks()
            html_parts.append('<hr class="page-break" />')
            continue

        unordered_match = re.match(r"^[-*+]\s+(.*)$", line)
        ordered_match = re.match(r"^\d+\.\s+(.*)$", line)
        if unordered_match or ordered_match:
            flush_paragraph()
            next_list_type = "ordered" if ordered_match else "unordered"
            if list_type and list_type != next_list_type:
                flush_list()
            list_type = next_list_type
            list_items.append([unordered_match.group(1) if unordered_match else ordered_match.group(1)])
            continue

        if list_type and list_items:
            list_items[-1].append(trimmed)
            continue

        paragraph_lines.append(trimmed)

    flush_code_block()
    flush_open_blocks()
    return "".join(html_parts)


def _wrap_html_document(fragment: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="sv">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Scenariorapport</title>
    <link rel="stylesheet" href="/frontend/styles.css" />
  </head>
  <body>
    <div class="page">
      <article class="panel report-text markdown-content">
        {fragment}
      </article>
    </div>
  </body>
</html>
"""


def _prepare_markdown_for_pandoc_html(markdown: str) -> str:
    return _PAGE_BREAK_PATTERN.sub(
        '<div class="page-break"></div>',
        markdown,
    )


def _prepare_markdown_for_pandoc_pdf(markdown: str, engine: str | None = None) -> str:
    if engine in _LATEX_PANDOC_PDF_ENGINES:
        return _PAGE_BREAK_PATTERN.sub(
            lambda _: "```{=latex}\n\\newpage\n```",
            markdown,
        )

    return _PAGE_BREAK_PATTERN.sub(
        lambda _: '<div style="page-break-after: always;"></div>',
        markdown,
    )


def _decorate_html_document(document: str) -> str:
    page_break_style = """
    <link rel="stylesheet" href="/frontend/styles.css" />
    <style>
      .page-break { break-after: page; page-break-after: always; }
      hr.page-break {
        border: 0;
        border-top: 2px dashed rgba(143, 109, 78, 0.35);
        margin: 2rem 0;
      }
      @media print {
        hr.page-break,
        div.page-break {
          border: 0;
          margin: 0;
        }
      }
    </style>
    """.strip()

    decorated = document.replace("<hr />", '<hr class="page-break" />')
    decorated = decorated.replace("<hr>", '<hr class="page-break">')
    if "</head>" in decorated:
        return decorated.replace("</head>", f"{page_break_style}\n</head>", 1)
    return decorated


def build_session_report_markdown(
    scenario: Scenario,
    session: SessionState,
    timeline: list[Turn],
    debrief: DebriefResponse,
) -> str:
    """Build the stored Markdown report for a completed session."""

    grouped_events: dict[int, list[str]] = {}
    for item in session.exercise_log:
        if item.type == "participant_action":
            continue
        grouped_events.setdefault(item.turn, []).append(
            f"- {item.type}: {_escape_markdown_text(item.text)}"
        )

    lines = [
        f"# Scenariorapport: {_escape_markdown_text(scenario.title)}",
        "",
        "## Scenarioinformation",
        "",
        f"- Scenario-id: `{scenario.id}`",
        f"- Version: `{scenario.version}`",
        f"- Publik: {', '.join(scenario.audiences)}",
        f"- Svårighetsgrad: {_escape_markdown_text(scenario.difficulty)}",
        f"- Tidsram: {scenario.timebox_minutes} min",
        f"- Session: `{session.session_id}`",
        f"- Status: `{session.status}`",
        f"- Slutfas: `{session.phase}`",
        f"- Sista tid: `{session.current_time}`",
        f"- Antal turns: {len(timeline)}",
        "",
        "### Beskrivning",
        "",
        _escape_markdown_text(scenario.description),
        "",
        "### Övningsmål",
        "",
        *_as_bullet_lines(list(scenario.training_goals), "- Inga övningsmål dokumenterade."),
        "",
        "---",
        "",
        "## Slutlig sessionsbild",
        "",
        "### Kända fakta",
        "",
        *_as_bullet_lines(session.known_facts, "- Inga sparade fakta."),
        "",
        "### Påverkade system",
        "",
        *_as_bullet_lines(session.affected_systems, "- Inga sparade system."),
        "",
        "### Konsekvenser",
        "",
        *_as_bullet_lines(session.consequences, "- Inga dokumenterade konsekvenser."),
        "",
        "## Debrief-underlag",
        "",
        "### Styrkor",
        "",
        *_as_bullet_lines(debrief.strengths, "- Inga styrkor dokumenterade."),
        "",
        "### Utvecklingsområden",
        "",
        *_as_bullet_lines(
            debrief.development_areas, "- Inga utvecklingsområden dokumenterade."
        ),
        "",
        "### Debriefingfrågor",
        "",
        *_as_bullet_lines(
            debrief.debrief_questions, "- Inga debriefingfrågor dokumenterade."
        ),
        "",
        "### Föreslagna uppföljningar",
        "",
        *_as_bullet_lines(
            debrief.recommended_follow_ups, "- Inga uppföljningar föreslagna."
        ),
        "",
        "### Facilitatornotering",
        "",
        _escape_markdown_text(debrief.facilitator_notes),
        "",
        "---",
        "",
        "## Summering med tidslinje",
        "",
        _escape_markdown_text(debrief.exercise_summary),
        "",
        "## Tidslinje",
    ]

    for turn in timeline:
        heading_id = _sanitize_heading_id(f"turn-{turn.turn_number}")
        lines.extend(
            [
                "",
                f"### Turn {turn.turn_number} - {turn.state_snapshot.current_time} {{#{heading_id}}}",
                "",
                "**Deltagaråtgärd**",
                "",
                _escape_markdown_text(turn.participant_input),
                "",
                "**Tolkad åtgärd**",
                "",
                _escape_markdown_text(turn.interpreted_action.action_summary),
                "",
                "**Lägesbild efter turn**",
                "",
                _escape_markdown_text(turn.narrator_response.situation_update),
            ]
        )
        turn_events = grouped_events.get(turn.turn_number, [])
        if turn_events:
            lines.extend(
                [
                    "",
                    "**System- och scenariohändelser**",
                    "",
                    *turn_events,
                ]
            )

    for item in debrief.timeline_summary:
        lines.extend(
            [
                f"### Turn {item.turn_number}",
                "",
                f"**Summering:** {_escape_markdown_text(item.summary)}",
                "",
                f"**Utfall:** {_escape_markdown_text(item.outcome)}",
                "",
            ]
        )

    lines.extend(["", "---", ""])

    if scenario.original_text:
        lines.extend(
            [
                "## Original text",
                "",
                scenario.original_text.strip(),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Original text",
                "",
                "Ingen originaltext sparad.",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _require_pandoc() -> str:
    pandoc_path = shutil.which("pandoc")
    if not pandoc_path:
        raise ReportRenderingError("Pandoc is not installed on the server.")
    return pandoc_path


def _get_available_pandoc_pdf_engine() -> str | None:
    for engine in _PANDOC_PDF_ENGINES:
        if shutil.which(engine):
            return engine
    return None


def _is_missing_pdf_engine_error(error: ReportRenderingError) -> bool:
    message = str(error).lower()
    return "pdf-engine" in message or "pdflatex not found" in message


def _run_pandoc(markdown: str, extra_args: list[str]) -> bytes:
    pandoc_path = _require_pandoc()
    from_format = _get_pandoc_from_format(extra_args)
    logger.info(
        "Running pandoc from_format=%s extra_args=%s",
        from_format,
        extra_args,
    )
    try:
        completed = subprocess.run(
            [pandoc_path, "--from", from_format, *extra_args],
            input=markdown.encode("utf-8"),
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else str(exc.stderr or "")
        ).strip()
        detail = stderr or "Pandoc conversion failed."
        raise ReportRenderingError(detail) from exc

    return completed.stdout


def _get_pandoc_from_format(extra_args: list[str]) -> str:
    if "--to" in extra_args:
        output_format = extra_args[extra_args.index("--to") + 1]
        if output_format == "pdf":
            return "markdown+raw_tex+raw_html+raw_attribute"
    return "gfm+raw_html"


def _render_inline_markdown_for_pdf(text: str) -> str:
    rendered = xml_escape(str(text))
    rendered = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+(?:\s+\"[^\"]*\")?)\)",
        lambda match: xml_escape(match.group(1)),
        rendered,
    )
    rendered = _STRONG_ASTERISK_PATTERN.sub(r"<b>\1</b>", rendered)
    rendered = _STRONG_UNDERSCORE_PATTERN.sub(r"<b>\1</b>", rendered)
    rendered = _EM_ASTERISK_PATTERN.sub(r"\1<i>\2</i>", rendered)
    rendered = _EM_UNDERSCORE_PATTERN.sub(r"\1<i>\2</i>", rendered)
    rendered = _STRIKE_PATTERN.sub(r"\1", rendered)
    rendered = _INLINE_CODE_PATTERN.sub(
        lambda match: f'<font face="Courier">{xml_escape(match.group(1))}</font>',
        rendered,
    )
    return rendered


def _render_markdown_to_pdf_with_reportlab(markdown: str) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            ListFlowable,
            ListItem,
            PageBreak,
            Paragraph,
            Preformatted,
            SimpleDocTemplate,
            Spacer,
        )
    except ImportError as exc:
        raise ReportRenderingError(
            "PDF export requires either a Pandoc PDF engine or the Python package reportlab."
        ) from exc

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Scenariorapport",
    )

    styles = getSampleStyleSheet()
    heading_styles = {
        1: ParagraphStyle(
            "ReportHeading1",
            parent=styles["Heading1"],
            fontSize=20,
            leading=24,
            spaceAfter=10,
        ),
        2: ParagraphStyle(
            "ReportHeading2",
            parent=styles["Heading2"],
            fontSize=16,
            leading=20,
            spaceBefore=10,
            spaceAfter=8,
        ),
        3: ParagraphStyle(
            "ReportHeading3",
            parent=styles["Heading3"],
            fontSize=13,
            leading=17,
            spaceBefore=8,
            spaceAfter=6,
        ),
    }
    paragraph_style = ParagraphStyle(
        "ReportParagraph",
        parent=styles["BodyText"],
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=7,
    )
    quote_style = ParagraphStyle(
        "ReportQuote",
        parent=paragraph_style,
        leftIndent=12,
        borderPadding=6,
        borderWidth=1,
        borderColor=colors.HexColor("#b08f72"),
        spaceBefore=4,
        spaceAfter=8,
    )
    code_style = ParagraphStyle(
        "ReportCode",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=9,
        leading=11,
        leftIndent=8,
        rightIndent=8,
        borderPadding=8,
        backColor=colors.HexColor("#f5efe8"),
        spaceBefore=4,
        spaceAfter=8,
    )
    
    story = []
    lines = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    paragraph_lines: list[str] = []
    quote_lines: list[str] = []
    list_items: list[str] = []
    ordered_list = False
    code_lines: list[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if not paragraph_lines:
            return
        text = "<br/>".join(_render_inline_markdown_for_pdf(line) for line in paragraph_lines)
        story.append(Paragraph(text, paragraph_style))
        paragraph_lines = []

    def flush_quote() -> None:
        nonlocal quote_lines
        if not quote_lines:
            return
        text = "<br/>".join(_render_inline_markdown_for_pdf(line) for line in quote_lines)
        story.append(Paragraph(text, quote_style))
        quote_lines = []

    def flush_list() -> None:
        nonlocal list_items, ordered_list
        if not list_items:
            return
        items = [
            ListItem(Paragraph(_render_inline_markdown_for_pdf(item), paragraph_style))
            for item in list_items
        ]
        story.append(
            ListFlowable(
                items,
                bulletType="1" if ordered_list else "bullet",
                start="1",
                leftIndent=18,
            )
        )
        story.append(Spacer(1, 4))
        list_items = []
        ordered_list = False

    def flush_code_block() -> None:
        nonlocal code_lines, in_code_block
        if not in_code_block:
            return
        story.append(Preformatted("\n".join(code_lines), code_style))
        code_lines = []
        in_code_block = False

    def flush_open_blocks() -> None:
        flush_paragraph()
        flush_quote()
        flush_list()

    for line in lines:
        trimmed = line.strip()

        if in_code_block:
            if trimmed.startswith("```"):
                flush_code_block()
            else:
                code_lines.append(line)
            continue

        if re.match(r"^```(\S+)?\s*$", line):
            flush_open_blocks()
            in_code_block = True
            continue

        if trimmed == "---":
            flush_open_blocks()
            story.append(PageBreak())
            continue

        if not trimmed:
            flush_open_blocks()
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading_match:
            flush_open_blocks()
            level = min(len(heading_match.group(1)), 3)
            story.append(
                Paragraph(
                    _render_inline_markdown_for_pdf(heading_match.group(2)),
                    heading_styles[level],
                )
            )
            continue

        quote_match = re.match(r"^>\s?(.*)$", line)
        if quote_match:
            flush_paragraph()
            flush_list()
            quote_lines.append(quote_match.group(1))
            continue

        unordered_match = re.match(r"^[-*+]\s+(.*)$", line)
        ordered_match = re.match(r"^\d+\.\s+(.*)$", line)
        if unordered_match or ordered_match:
            flush_paragraph()
            flush_quote()
            is_ordered = ordered_match is not None
            if list_items and ordered_list != is_ordered:
                flush_list()
            ordered_list = is_ordered
            list_items.append(
                unordered_match.group(1) if unordered_match else ordered_match.group(1)
            )
            continue

        if list_items:
            list_items[-1] = f"{list_items[-1]} {trimmed}"
            continue

        paragraph_lines.append(trimmed)

    flush_code_block()
    flush_open_blocks()
    document.build(story)
    return buffer.getvalue()


def render_markdown_to_html(markdown: str) -> str:
    """Convert Markdown to standalone HTML using pandoc."""

    try:
        logger.info("Rendering report HTML with pandoc")
        html_bytes = _run_pandoc(
            _prepare_markdown_for_pandoc_html(markdown),
            ["--to", "html5", "--standalone"],
        )
        return _decorate_html_document(html_bytes.decode("utf-8"))
    except ReportRenderingError as exc:
        if "not installed" not in str(exc).lower():
            raise
        logger.info("Rendering report HTML with local markdown fallback")
        return _wrap_html_document(_render_markdown_fragment(markdown))


def render_markdown_to_pdf(markdown: str) -> bytes:
    """Convert Markdown to PDF using pandoc."""

    engine = _get_available_pandoc_pdf_engine()

    if engine:
        logger.info("Rendering report PDF with pandoc engine=%s", engine)
        prepared_markdown = _prepare_markdown_for_pandoc_pdf(markdown, engine)
        try:
            return _run_pandoc(
                prepared_markdown,
                ["--to", "pdf", "--output", "-", "--pdf-engine", engine],
            )
        except ReportRenderingError as exc:
            if not _is_missing_pdf_engine_error(exc):
                raise
            logger.warning(
                "Pandoc PDF engine failed due to missing engine dependency engine=%s detail=%s",
                engine,
                exc,
            )

    logger.info("Rendering report PDF with reportlab fallback")
    return _render_markdown_to_pdf_with_reportlab(markdown)
