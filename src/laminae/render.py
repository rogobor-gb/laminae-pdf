"""Render a report IR to a LaTeX source string.

The renderer is a *total* function over the algebra of the IR: it dispatches
on the ``kind`` discriminator of each slide (case analysis on the coproduct
defined in :mod:`laminae.ir`) and folds the resulting fragments into a body,
which a Jinja skeleton wraps in a template-specific preamble.

Two deliberate decoupling choices
---------------------------------
1. **No run-time dependency on the schema library.** This module accesses
   only the *structure* of the IR (attribute access and the ``kind`` tag),
   never :mod:`pydantic`. The validation library belongs at the ingress
   boundary; the renderer depends on the shape of the data, not on how it
   was validated. This keeps the trusted rendering core dependency-light
   (Jinja2 only) and independently testable with any duck-typed object.
2. **Escaping is centralised here, not in the templates.** Every string that
   originates from the plan passes through :func:`laminae.latex.escape_latex`
   in this module before reaching a template. Templates receive only strings
   that are already valid LaTeX and insert them verbatim, so the safety
   property is auditable in one place.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .latex import escape_latex

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids importing pydantic
    from .ir import Report

__all__ = ["render_tex", "render_to_file", "TEMPLATES_DIR", "RenderError"]

#: Directory holding the shipped Jinja/LaTeX templates.
TEMPLATES_DIR: Path = Path(__file__).parent / "templates"

#: Beamer block environment names keyed by the IR's ``block`` value.
_BLOCK_ENVIRONMENTS: dict[str, str] = {
    "block": "block",
    "alert": "alertblock",
    "example": "exampleblock",
}

# Jinja delimiters are redefined so they do not collide with LaTeX braces.
# This is the standard LaTeX/Jinja recipe; ``\VAR{x}`` interpolates and
# ``\BLOCK{...}`` carries control flow.
_LATEX_JINJA_SYNTAX: dict[str, Any] = {
    "block_start_string": r"\BLOCK{",
    "block_end_string": "}",
    "variable_start_string": r"\VAR{",
    "variable_end_string": "}",
    "comment_start_string": r"\#{",
    "comment_end_string": "}",
    "line_statement_prefix": "%%",
    "line_comment_prefix": "%#",
    "trim_blocks": True,
    "lstrip_blocks": True,
    "autoescape": False,
    "undefined": StrictUndefined,
}


class RenderError(RuntimeError):
    """Raised when a report cannot be rendered to LaTeX."""


# --------------------------------------------------------------------------- #
# Frame helpers
# --------------------------------------------------------------------------- #
def _frame_title(title: str | None) -> str:
    """Return a beamer frame-title argument, escaped, or the empty string."""
    return "" if not title else "{" + escape_latex(title) + "}"


def _begin_frame(title: str | None) -> str:
    return "\\begin{frame}" + _frame_title(title) + "\n"


def _end_frame() -> str:
    return "\\end{frame}\n"


# --------------------------------------------------------------------------- #
# Per-variant renderers (case analysis on the coproduct tag)
# --------------------------------------------------------------------------- #
def _render_section(slide: Any) -> str:
    return "\\section{" + escape_latex(slide.title) + "}\n"


def _render_prose(slide: Any) -> str:
    parts = [_begin_frame(slide.title)]
    environment = _BLOCK_ENVIRONMENTS.get(slide.block)
    if environment is not None:
        block_title = escape_latex(slide.block_title) if slide.block_title else ""
        parts.append(f"\\begin{{{environment}}}{{{block_title}}}\n")
    parts.append(escape_latex(slide.body) + "\n")
    if environment is not None:
        parts.append(f"\\end{{{environment}}}\n")
    parts.append(_end_frame())
    return "".join(parts)


def _render_figure(slide: Any, contents_ref: str) -> str:
    graphic = f"{contents_ref}/{slide.path}"
    if slide.full_frame:
        return (
            "{%\n"
            "\\setbeamertemplate{navigation symbols}{}\n"
            "\\begin{frame}[plain]\n"
            "\\centering\n"
            "\\includegraphics[width=\\paperwidth,height=\\paperheight,"
            "keepaspectratio]{" + graphic + "}\n"
            "\\end{frame}\n"
            "}\n"
        )
    parts = [
        _begin_frame(slide.title),
        "\\begin{figure}\n\\centering\n",
        "\\includegraphics[width=\\linewidth,height=0.78\\textheight,"
        "keepaspectratio]{" + graphic + "}\n",
    ]
    if slide.caption:
        parts.append("\\caption{" + escape_latex(slide.caption) + "}\n")
    parts.append("\\end{figure}\n")
    parts.append(_end_frame())
    return "".join(parts)


def _read_csv(path: Path) -> list[list[str]]:
    if not path.is_file():
        raise RenderError(f"CSV not found for table slide: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.reader(handle) if row]
    if not rows:
        raise RenderError(f"CSV is empty: {path}")
    return rows


def _column_format(slide: Any, ncols: int) -> str:
    if slide.column_format:
        return slide.column_format
    if slide.first_col_is_index and ncols >= 1:
        return "l" + "r" * (ncols - 1)
    return "l" * ncols


def _render_row(cells: list[str], *, bold: bool = False) -> str:
    rendered = [escape_latex(cell) for cell in cells]
    if bold:
        rendered = ["{\\bfseries " + cell + "}" for cell in rendered]
    return " & ".join(rendered) + r" \\"


def _render_table(slide: Any, contents_dir: Path) -> str:
    rows = _read_csv(contents_dir / slide.path)
    ncols = max(len(row) for row in rows)
    rows = [row + [""] * (ncols - len(row)) for row in rows]  # pad ragged rows

    header = rows[0] if slide.use_header else None
    data = rows[1:] if slide.use_header else rows

    lines = [
        "\\begin{tabular}{" + _column_format(slide, ncols) + "}",
        "\\toprule",
    ]
    if header is not None:
        lines.append(_render_row(header))
        lines.append("\\midrule")
    for i, row in enumerate(data):
        is_last = i == len(data) - 1
        if is_last and slide.highlight_last_row:
            lines.append("\\midrule")
            lines.append(_render_row(row, bold=True))
        else:
            lines.append(_render_row(row))
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    tabular = "\n".join(lines)

    # Shrink to the text width only if the natural width would overflow.
    boxed = (
        "\\resizebox{\\ifdim\\width>\\linewidth\\linewidth\\else\\width\\fi}{!}{%\n"
        + tabular
        + "\n}"
    )
    return (
        _begin_frame(slide.title)
        + "\\begin{table}\n\\centering\n"
        + boxed
        + "\n\\end{table}\n"
        + _end_frame()
    )


def _render_raw(slide: Any) -> str:
    # Trusted verbatim insertion. See laminae.ir.RawLatexSlide.
    return "\\begin{frame}\n" + slide.body + "\n\\end{frame}\n"


_DISPATCH = {
    "section": lambda s, ctx: _render_section(s),
    "prose": lambda s, ctx: _render_prose(s),
    "figure": lambda s, ctx: _render_figure(s, ctx["contents_ref"]),
    "table": lambda s, ctx: _render_table(s, ctx["contents_dir"]),
    "raw": lambda s, ctx: _render_raw(s),
}

_SEPARATOR = "\n" + "%" + "-" * 78 + "\n"


def _render_body(report: "Report", contents_dir: Path, contents_ref: str) -> str:
    context = {"contents_dir": contents_dir, "contents_ref": contents_ref}
    fragments = []
    for index, slide in enumerate(report.slides):
        handler = _DISPATCH.get(slide.kind)
        if handler is None:  # unreachable if IR and dispatch stay in sync
            raise RenderError(f"No renderer for slide {index} of kind {slide.kind!r}")
        fragments.append(handler(slide, context))
    return _SEPARATOR.join(fragments)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def render_tex(
    report: "Report",
    *,
    contents_dir: Path | str,
    template_dir: Path | str | None = None,
    contents_ref: str = "contents",
) -> str:
    """Render a report to a LaTeX source string.

    Parameters
    ----------
    report : Report
        The report to render. Only its structure is used (attribute access
        and the ``kind`` discriminator); the concrete class is irrelevant.
    contents_dir : pathlib.Path or str
        Directory from which table CSVs are read at render time. Figure
        assets are referenced by relative path and resolved at compile time.
    template_dir : pathlib.Path or str, optional
        Directory containing ``clean.tex.j2`` and ``accent.tex.j2``.
        Defaults to the shipped :data:`TEMPLATES_DIR`.
    contents_ref : str, optional
        Relative path prefix used inside the ``.tex`` for figure assets
        (must match the on-disk layout at compile time). Defaults to
        ``"contents"``.

    Returns
    -------
    str
        Complete LaTeX source ready to be written to disk and compiled.

    Raises
    ------
    RenderError
        If a table CSV is missing/empty or a slide kind has no renderer.
    """
    contents_dir = Path(contents_dir)
    template_dir = Path(template_dir) if template_dir is not None else TEMPLATES_DIR

    body = _render_body(report, contents_dir, contents_ref)

    environment = Environment(
        loader=FileSystemLoader(str(template_dir)), **_LATEX_JINJA_SYNTAX
    )
    template = environment.get_template(f"{report.template}.tex.j2")

    context = {
        "title": escape_latex(report.title),
        "author": escape_latex(report.author) if report.author else "",
        "date": escape_latex(report.date) if report.date else r"\today",
        "institution": (
            escape_latex(report.institution) if report.institution else ""
        ),
        "include_toc": bool(report.include_toc),
        "body": body,  # already valid LaTeX; inserted verbatim
    }
    return template.render(**context)


def render_to_file(
    report: "Report",
    out_dir: Path | str,
    *,
    template_dir: Path | str | None = None,
    filename: str | None = None,
) -> Path:
    """Render a report and write the ``.tex`` file to ``out_dir``.

    Table CSVs and figure assets are expected under ``out_dir/contents``.

    Parameters
    ----------
    report : Report
        The report to render.
    out_dir : pathlib.Path or str
        Output directory. Created if it does not exist. The ``.tex`` file is
        written here and ``out_dir/contents`` is used for assets.
    template_dir : pathlib.Path or str, optional
        Override for the template directory.
    filename : str, optional
        Output ``.tex`` filename. Defaults to ``"report.tex"``.

    Returns
    -------
    pathlib.Path
        Path to the written ``.tex`` file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    contents_dir = out_dir / "contents"
    contents_dir.mkdir(exist_ok=True)

    tex_source = render_tex(
        report, contents_dir=contents_dir, template_dir=template_dir
    )
    tex_path = out_dir / (filename or "report.tex")
    tex_path.write_text(tex_source, encoding="utf-8")
    return tex_path
