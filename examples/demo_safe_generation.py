"""End-to-end demo: build a typed report, render, and compile to PDF.

The prose slide deliberately contains every LaTeX special character to show
that untrusted narrative is neutralised at the rendering boundary, while the
figure and table come from deterministic code. Requires ``pydantic`` and (for
the generated assets) ``numpy`` + ``matplotlib``; needs a LaTeX engine
(XeLaTeX) on PATH to produce the PDF.

Run
---
    python examples/demo_safe_generation.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from laminae import (  # noqa: E402
    FigureSlide,
    ProseSlide,
    Report,
    SectionSlide,
    TableSlide,
    compile_pdf,
    render_to_file,
)

OUT_DIR = Path(__file__).resolve().parent / "output"
CONTENTS = OUT_DIR / "contents"


def _write_assets() -> None:
    """Generate a figure and a CSV under ``OUT_DIR/contents``."""
    CONTENTS.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    t = np.linspace(0.0, 1.0, 252)
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    for _ in range(6):
        increments = rng.normal(0.0, np.sqrt(1.0 / 252), 252)
        walk = np.cumsum(increments)
        ax.plot(t, walk - t * walk[-1], linewidth=1.0)
    ax.set_title("Brownian bridge realisations")
    ax.set_xlabel("t")
    ax.set_ylabel("B(t)")
    fig.tight_layout()
    fig.savefig(CONTENTS / "bridges.png", dpi=130)
    plt.close(fig)

    (CONTENTS / "stats.csv").write_text(
        "Statistic,Value\n"
        "Mean of max,0.6267\n"
        "Std of max,0.2410\n"
        "Share > 0 (%),100%\n"
        "Total,1.0000\n",
        encoding="utf-8",
    )


def build_report() -> Report:
    """Assemble a validated report mixing generated and narrative content."""
    hostile = (
        "Return was 12% on fund_A & fund_B; note $x^2$, a #hashtag, "
        "braces {like this}, a tilde ~, and a stray backslash \\ end."
    )
    return Report(
        title="Safe Generation Demo: 100% & Fund_A",
        author="G. Breschi",
        institution="Portfolio Research",
        template="accent",
        include_toc=True,
        slides=[
            SectionSlide(title="Narrative (untrusted text)"),
            ProseSlide(
                title="Escaping stress test",
                body=hostile,
                block="alert",
                block_title="All specials survive: _ % & # $ { } ~ ^ \\",
            ),
            SectionSlide(title="Deterministic content"),
            FigureSlide(
                title="Simulated paths",
                path="bridges.png",
                caption="Six bridges; caption with 50% & a _score.",
            ),
            TableSlide(
                title="Summary statistics",
                path="stats.csv",
                first_col_is_index=True,
                highlight_last_row=True,
            ),
        ],
    )


def main() -> None:
    _write_assets()
    report = build_report()
    tex_path = render_to_file(report, OUT_DIR, filename="demo.tex")
    print(f"Rendered LaTeX: {tex_path}")
    pdf_path = compile_pdf(tex_path, engine="xelatex")
    print(f"Compiled PDF:   {pdf_path}")


if __name__ == "__main__":
    main()
