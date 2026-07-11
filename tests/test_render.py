"""Tests for :mod:`laminae.render`.

These use ``types.SimpleNamespace`` stand-ins rather than the pydantic IR, to
document and enforce that the renderer depends only on the *structure* of the
IR (attribute access and the ``kind`` tag), not on the validation library.
"""

from pathlib import Path
from types import SimpleNamespace as NS

from laminae.render import render_tex


def _base_report(slides: list, template: str = "clean") -> NS:
    return NS(
        title="T",
        author="A",
        date=None,
        institution=None,
        template=template,
        include_toc=False,
        slides=slides,
    )


def test_prose_body_is_escaped(tmp_path: Path) -> None:
    report = _base_report(
        [NS(kind="prose", title="X", body="a & b_c 100%", block="none",
            block_title=None)]
    )
    tex = render_tex(report, contents_dir=tmp_path)
    assert r"a \& b\_c 100\%" in tex
    # The bare specials must not appear in the emitted body.
    assert "a & b_c" not in tex


def test_title_is_escaped(tmp_path: Path) -> None:
    report = _base_report([])
    report.title = "Fund_A & 100%"
    tex = render_tex(report, contents_dir=tmp_path)
    assert r"\title{Fund\_A \& 100\%}" in tex


def test_table_renders_booktabs_and_highlights_last_row(tmp_path: Path) -> None:
    (tmp_path / "t.csv").write_text("Name,Value\nAlpha,1\nTotal,3\n", encoding="utf-8")
    report = _base_report(
        [NS(kind="table", title=None, path="t.csv", use_header=True,
            first_col_is_index=True, column_format=None, highlight_last_row=True)]
    )
    tex = render_tex(report, contents_dir=tmp_path)
    assert "\\toprule" in tex and "\\bottomrule" in tex
    assert "{\\bfseries Total}" in tex  # last row bolded


def test_figure_reference_uses_contents_prefix(tmp_path: Path) -> None:
    report = _base_report(
        [NS(kind="figure", title="F", path="p.png", caption=None,
            full_frame=False)]
    )
    tex = render_tex(report, contents_dir=tmp_path)
    assert "{contents/p.png}" in tex


def test_accent_template_selects_pagella(tmp_path: Path) -> None:
    tex = render_tex(_base_report([], template="accent"), contents_dir=tmp_path)
    assert "TeX Gyre Pagella" in tex
