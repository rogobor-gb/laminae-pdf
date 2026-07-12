# laminae

Safe, auditable generation of LaTeX/Beamer documents from a **typed intermediate
representation (IR)**. `laminae` is designed for the setting where part of a
document is produced deterministically by code (figures, tables, computed
numbers) and part is authored by a language model (narrative prose).

Its central design rule:

> **The model never emits LaTeX. It emits a validated instance of the IR.
> Prose is treated as data and escaped at the rendering boundary.**

This buys determinism, auditability, and immunity to LaTeX injection from model
output, while cleanly separating *what to say* (the plan) from *how it is typeset*
(the renderer).

## Pipeline

```
data ── your analysis code ──▶ figures + tables (+ a "facts" table)
                                     │
     facts + brief ── LLM (structured output) ──▶ ReportPlan   (validated IR)
                                     │
                     Report ── render (pure) ──▶ .tex ── compile ──▶ PDF
```

* `laminae.ir` — the typed IR. `ReportPlan` is the **LLM-facing** schema
  (`ReportPlan.model_json_schema()` is the structured-output contract); `Report`
  is the **renderer-facing** type that trusted code may widen with a verbatim
  LaTeX escape hatch.
* `laminae.render` — a pure, total function `Report → LaTeX`. Depends only on
  the *structure* of the IR, not on the validation library.
* `laminae.compile` — a reentrant LaTeX→PDF compiler that never calls
  `os.chdir` (working directory is passed via `subprocess`'s `cwd`), so it is
  safe under concurrency and repeated agentic invocation.

## Quickstart

```python
from laminae import Report, SectionSlide, ProseSlide, TableSlide, render_to_file, compile_pdf

report = Report(
    title="Monthly Commentary",
    template="accent",                       # "clean" | "accent" | "ember"
    slides=[
        SectionSlide(title="Overview"),
        ProseSlide(title="Summary", body="Tracking error fell to 42 bps..."),
        TableSlide(title="Exposures", path="exposures.csv", highlight_last_row=True),
    ],
)

tex = render_to_file(report, "build/", filename="report.tex")   # assets in build/contents/
pdf = compile_pdf(tex, engine="xelatex")
```

See `examples/demo_safe_generation.py` for a runnable end-to-end example that
feeds every LaTeX special character through the prose path and still compiles.

## The safety property, precisely

Let `S = { \  &  %  $  #  _  {  }  ~  ^ }` be the text-mode special characters
and `σ : S → Σ*` the escape map (image may re-contain symbols of `S`, e.g.
`\textbackslash{}`). The naive fold of per-character replacements

```
R = r_{c_n} ∘ … ∘ r_{c_1},   r_c(w) = w[c ↦ σ(c)]
```

is **incorrect**: `σ(c)` reintroduces characters of `S` that later factors
re-process, so `R` is order-dependent (escaping `\` first, then `{`/`}`,
corrupts the `\textbackslash{}` just inserted). `laminae.latex.escape_latex`
instead performs a single leftmost, non-overlapping scan of the *input* and
applies `σ` pointwise, so every original special character is replaced exactly
once and no inserted character is ever re-scanned. `tests/test_latex.py` pins
this property.

## Why a tagged union for the IR

A slide is a coproduct `Section ⊕ Prose ⊕ Figure ⊕ Table ⊕ Markdown ⊕ Raw`
tagged by `kind`, and a report is `Metadata × List(Slide)`. Rendering is then
a *total* function defined by case analysis on the tag. Adding a variant
forces a new render case, so exhaustiveness is a type-level property rather
than a runtime invariant (contrast the fragile `n_slides == len(dict) - 1`
check that ad-hoc dictionaries need). The trust boundary is also encoded in
types: `RawLatexSlide` (verbatim LaTeX) and `MarkdownSlide` (parsed by the
LaTeX `markdown` package rather than escaped) are both excluded from
`PlannableSlide`, hence from the LLM schema — only trusted code may emit them.

## Install

```bash
pip install -e .              # core: jinja2 + pydantic
pip install -e ".[demo,test]" # + numpy/matplotlib for the demo, pytest for tests
```

Requires a LaTeX distribution with XeLaTeX (TeX Live / MiKTeX) on `PATH`, plus
the `markdown` CTAN package (for `MarkdownSlide`). The `clean` and `accent`
templates use only fonts that ship with TeX Live (Latin Modern and TeX Gyre,
respectively), so they build on a stock installation with no proprietary
fonts. `ember` — ported from the original beamerfy `chessOrange` template —
additionally requires the system fonts Palatino, Helvetica, and Monaco.

## Tests

```bash
pytest
```

`test_latex.py` and `test_render.py` need no LaTeX engine and no pydantic
(the renderer is validated with duck-typed stand-ins); `test_ir.py` exercises
the pydantic validation and is skipped where pydantic is absent.
