"""Tests for :mod:`laminae.ir` (require pydantic).

Skipped automatically where pydantic is not installed.
"""

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError  # noqa: E402

from laminae.ir import RawLatexSlide, Report, ReportPlan  # noqa: E402


def test_plan_schema_excludes_raw_latex() -> None:
    # The LLM-facing schema must not permit the verbatim escape hatch.
    schema_text = str(ReportPlan.model_json_schema())
    assert "raw" not in schema_text or "RawLatexSlide" not in schema_text


def test_report_admits_raw_but_plan_does_not() -> None:
    raw = {"kind": "raw", "body": "\\pause"}
    Report(title="t", slides=[raw])  # accepted by the renderer-facing type
    with pytest.raises(ValidationError):
        ReportPlan(title="t", slides=[raw])  # rejected by the LLM-facing type


def test_path_traversal_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReportPlan(
            title="t",
            slides=[{"kind": "figure", "path": "../secret.png"}],
        )


def test_unsafe_path_characters_rejected() -> None:
    with pytest.raises(ValidationError):
        ReportPlan(
            title="t",
            slides=[{"kind": "figure", "path": "a b{c}.png"}],
        )


def test_extra_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        ReportPlan(title="t", author="a", surprise="x")


def test_from_plan_upcasts() -> None:
    plan = ReportPlan(title="t", slides=[{"kind": "section", "title": "S"}])
    report = Report.from_plan(plan)
    assert isinstance(report, Report)
    assert report.slides[0].title == "S"


def test_raw_latex_slide_is_verbatim_typed() -> None:
    slide = RawLatexSlide(body="\\pause")
    assert slide.kind == "raw"
