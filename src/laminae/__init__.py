"""laminae: safe, auditable generation of LaTeX/Beamer documents from a typed IR.

The public surface separates three stages:

* :mod:`laminae.ir` — the typed intermediate representation. ``ReportPlan`` is
  the LLM-facing schema; ``Report`` is the renderer-facing type.
* :mod:`laminae.render` — a total function ``Report -> LaTeX`` with all
  untrusted text escaped at the boundary.
* :mod:`laminae.compile` — a reentrant LaTeX-to-PDF compiler (no ``os.chdir``).
"""

from __future__ import annotations

from .compile import CompilationError, compile_pdf
from .ir import (
    AnySlide,
    FigureSlide,
    PlannableSlide,
    ProseSlide,
    RawLatexSlide,
    Report,
    ReportPlan,
    SectionSlide,
    TableSlide,
)
from .latex import escape_latex
from .render import RenderError, render_tex, render_to_file

__all__ = [
    # IR
    "ReportPlan",
    "Report",
    "SectionSlide",
    "ProseSlide",
    "FigureSlide",
    "TableSlide",
    "RawLatexSlide",
    "PlannableSlide",
    "AnySlide",
    # rendering
    "render_tex",
    "render_to_file",
    "RenderError",
    "escape_latex",
    # compilation
    "compile_pdf",
    "CompilationError",
]

__version__ = "0.1.0"
