"""Tests for :mod:`laminae.latex`."""

from laminae.latex import LATEX_SPECIAL, escape_latex


def test_each_special_maps_to_its_escape() -> None:
    for raw, escaped in LATEX_SPECIAL.items():
        assert escape_latex(raw) == escaped


def test_plain_text_is_unchanged() -> None:
    text = "Sharpe ratio 1.4, no special characters here."
    assert escape_latex(text) == text


def test_inserted_characters_are_not_re_escaped() -> None:
    # The core correctness property: escaping the backslash introduces braces
    # (\textbackslash{}) which must NOT themselves be escaped. A naive fold of
    # per-character str.replace calls would corrupt this; the single-pass scan
    # does not, because it matches positions in the *input* only.
    assert escape_latex("\\") == r"\textbackslash{}"
    assert escape_latex("{") == r"\{"
    assert escape_latex("\\{") == r"\textbackslash{}\{"


def test_realistic_financial_string() -> None:
    result = escape_latex("100% of AUM in fund_A & fund_B")
    assert result == r"100\% of AUM in fund\_A \& fund\_B"
    for forbidden in ("%", "_", "&"):
        # No *bare* special remains (every occurrence is preceded by a backslash).
        assert f" {forbidden}" not in result.replace("\\" + forbidden, "")
