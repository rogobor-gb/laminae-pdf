"""Typed intermediate representation (IR) for a report / slide deck.

The IR is the interface between three concerns that are otherwise easy to
entangle:

1. *Deterministic quantitative content* — figures and tables produced by
   trusted analysis code.
2. *Generated narrative* — prose authored by a language model.
3. *Rendering* — the deterministic mapping of the plan to LaTeX.

Design rationale
----------------
A slide is modelled as a **tagged sum type** (a discriminated union)

.. math::

    \\mathrm{Slide}
    \\;=\\;
    \\mathrm{Section}
    \\,\\oplus\\,
    \\mathrm{Prose}
    \\,\\oplus\\,
    \\mathrm{Figure}
    \\,\\oplus\\,
    \\mathrm{Table}
    \\,\\oplus\\,
    \\mathrm{Raw},

with the field ``kind`` acting as the coproduct tag, and a report as
:math:`\\mathrm{Metadata} \\times \\mathrm{List}(\\mathrm{Slide})`.
Rendering is then a *total* function defined by case analysis on the tag
(see :mod:`laminae.render`); adding a variant forces a new case, so
exhaustiveness is enforced structurally rather than by a run-time invariant
such as the ``n_slides == len(dict) - 1`` check used by ad-hoc dictionaries.

Trust boundary
--------------
The escape hatch :class:`RawLatexSlide` bypasses escaping and must therefore
never be populated from untrusted input. This is encoded in the type system
by exposing two report classes:

* :class:`ReportPlan` — ``slides: list[PlannableSlide]``; excludes the raw
  escape hatch. Its JSON schema (``ReportPlan.model_json_schema()``) is the
  contract handed to a language model for structured output.
* :class:`Report` — ``slides: list[AnySlide]``; the renderer-facing type
  that *trusted* code may widen with :class:`RawLatexSlide`.

A model can therefore only ever emit ``PlannableSlide`` instances, and
:meth:`Report.from_plan` upcasts a validated plan for rendering.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "SectionSlide",
    "ProseSlide",
    "FigureSlide",
    "TableSlide",
    "RawLatexSlide",
    "PlannableSlide",
    "AnySlide",
    "ReportPlan",
    "Report",
]

# A conservative filename grammar for assets referenced from the deck. It
# forbids whitespace, LaTeX-breaking characters, and (via the validator
# below) parent-directory traversal. Assets are produced by trusted code, so
# this closes a path-injection vector even when the *plan* is model-authored.
_SAFE_PATH_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._\-/]*$"


class _SlideBase(BaseModel):
    """Common configuration for all slide variants."""

    model_config = {"extra": "forbid"}


class SectionSlide(_SlideBase):
    """A section divider that also creates a table-of-contents entry.

    Parameters
    ----------
    title : str
        Section heading. Escaped at render time.
    """

    kind: Literal["section"] = "section"
    title: str


class ProseSlide(_SlideBase):
    """A slide carrying narrative text, optionally inside a beamer block.

    Parameters
    ----------
    title : str or None, optional
        Frame title. ``None`` produces an untitled frame.
    body : str
        Narrative text. Treated as *data*: escaped at render time. Blank
        lines are interpreted by LaTeX as paragraph breaks.
    block : {"none", "block", "alert", "example"}, optional
        Beamer block environment wrapping the body. ``"none"`` renders the
        body directly on the frame.
    block_title : str or None, optional
        Title of the block environment (ignored when ``block == "none"``).
    """

    kind: Literal["prose"] = "prose"
    title: str | None = None
    body: str
    block: Literal["none", "block", "alert", "example"] = "block"
    block_title: str | None = None


class FigureSlide(_SlideBase):
    """A slide displaying a single raster/vector figure.

    Parameters
    ----------
    title : str or None, optional
        Frame title.
    path : str
        Filename of the figure relative to the deck's ``contents`` folder.
        Constrained by :data:`_SAFE_PATH_PATTERN`.
    caption : str or None, optional
        Figure caption. Escaped at render time.
    full_frame : bool, optional
        If ``True``, the figure fills the whole slide (no title, no chrome).
    """

    kind: Literal["figure"] = "figure"
    title: str | None = None
    path: str = Field(pattern=_SAFE_PATH_PATTERN)
    caption: str | None = None
    full_frame: bool = False

    @field_validator("path")
    @classmethod
    def _forbid_traversal(cls, value: str) -> str:
        if ".." in value:
            raise ValueError("path must not contain parent-directory traversal '..'")
        return value


class TableSlide(_SlideBase):
    """A slide rendering a CSV file as a booktabs table.

    Parameters
    ----------
    title : str or None, optional
        Frame title.
    path : str
        Filename of the CSV relative to the deck's ``contents`` folder.
        Constrained by :data:`_SAFE_PATH_PATTERN`.
    use_header : bool, optional
        Treat the first CSV row as a header (rendered above a ``\\midrule``).
    first_col_is_index : bool, optional
        Treat the first column as a row label; affects only the default
        column alignment (``l`` for the first column, ``r`` thereafter).
    column_format : str or None, optional
        Explicit LaTeX column specification (e.g. ``"lrr"``). Overrides the
        alignment inferred from ``first_col_is_index``.
    highlight_last_row : bool, optional
        Bold the final data row and precede it with a ``\\midrule`` (useful
        for totals / summary rows).
    """

    kind: Literal["table"] = "table"
    title: str | None = None
    path: str = Field(pattern=_SAFE_PATH_PATTERN)
    use_header: bool = True
    first_col_is_index: bool = False
    column_format: str | None = None
    highlight_last_row: bool = False

    @field_validator("path")
    @classmethod
    def _forbid_traversal(cls, value: str) -> str:
        if ".." in value:
            raise ValueError("path must not contain parent-directory traversal '..'")
        return value


class RawLatexSlide(_SlideBase):
    """Verbatim LaTeX escape hatch — **trusted input only**.

    The ``body`` is inserted into the document without any escaping. It must
    never be populated from untrusted or model-generated input. This variant
    is deliberately excluded from :data:`PlannableSlide` (and therefore from
    the LLM-facing JSON schema).

    Parameters
    ----------
    body : str
        Raw LaTeX inserted verbatim between two frame boundaries.
    """

    kind: Literal["raw"] = "raw"
    body: str


#: Slides a language model is permitted to emit (no raw-LaTeX escape hatch).
PlannableSlide = Annotated[
    Union[SectionSlide, ProseSlide, FigureSlide, TableSlide],
    Field(discriminator="kind"),
]

#: All slides the renderer accepts, including the trusted raw escape hatch.
AnySlide = Annotated[
    Union[SectionSlide, ProseSlide, FigureSlide, TableSlide, RawLatexSlide],
    Field(discriminator="kind"),
]


class ReportPlan(BaseModel):
    """A validated report skeleton an LLM is allowed to emit.

    ``ReportPlan.model_json_schema()`` is the structured-output contract for
    the plan-building agent: it excludes :class:`RawLatexSlide`, so the model
    cannot inject verbatim LaTeX.

    Parameters
    ----------
    title : str
        Document title.
    author : str, optional
        Document author.
    date : str or None, optional
        Document date. ``None`` defaults to LaTeX ``\\today`` at render time.
    institution : str or None, optional
        Optional affiliation shown on the title page.
    template : {"clean", "accent"}, optional
        Presentational template (preamble/theme only).
    include_toc : bool, optional
        Emit a table-of-contents frame after the title page.
    slides : list of PlannableSlide, optional
        Ordered slide plan.
    """

    model_config = {"extra": "forbid"}

    title: str
    author: str = ""
    date: str | None = None
    institution: str | None = None
    template: Literal["clean", "accent"] = "clean"
    include_toc: bool = True
    slides: list[PlannableSlide] = Field(default_factory=list)


class Report(ReportPlan):
    """Renderer-facing report; trusted code may include raw LaTeX slides.

    Widens :attr:`ReportPlan.slides` to :data:`AnySlide`.
    """

    slides: list[AnySlide] = Field(default_factory=list)

    @classmethod
    def from_plan(cls, plan: ReportPlan) -> "Report":
        """Upcast a validated :class:`ReportPlan` to a :class:`Report`.

        Parameters
        ----------
        plan : ReportPlan
            A validated plan, typically produced by an LLM.

        Returns
        -------
        Report
            An equivalent report accepted by the renderer.
        """
        return cls.model_validate(plan.model_dump())
