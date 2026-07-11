"""LaTeX-safe escaping of untrusted (e.g. model-generated) text.

This module isolates the single most safety-critical operation in the
pipeline: neutralising the LaTeX special characters in any string that
originates outside the trusted code path — in particular, narrative prose
emitted by a language model.

Notes
-----
Let :math:`S = \\{\\,\\backslash,\\&,\\%,\\$,\\#,\\_,\\{,\\},\\sim,\\wedge\\,\\}`
be the set of the ten text-mode special characters, and let
:math:`\\sigma : S \\to \\Sigma^{*}` map each to its escaped form (its image
may itself contain symbols of :math:`S`, e.g. ``\\textbackslash{}`` contains
both a backslash and braces). The *naive* implementation folds a family of
per-character replacements

.. math::

    r_{c}(w) = w[\\,c \\mapsto \\sigma(c)\\,],
    \\qquad
    R = r_{c_{n}} \\circ \\cdots \\circ r_{c_{1}},

which is **not** the intended map, because :math:`\\sigma(c)` reintroduces
characters of :math:`S` that later factors :math:`r_{c'}` re-process. The
composition is order-dependent and non-idempotent; e.g. escaping the
backslash first, then the braces, corrupts the ``\\textbackslash{}`` just
inserted.

The correct construction performs a single leftmost, non-overlapping scan
of the *input* and applies :math:`\\sigma` pointwise. Matches are taken over
the original string only, so every original special character is replaced
exactly once and no inserted character is ever re-scanned. This is what
``re.Pattern.sub`` guarantees, and it is the implementation used below.
"""

from __future__ import annotations

import re

__all__ = ["escape_latex", "LATEX_SPECIAL"]

#: Mapping from each LaTeX text-mode special character to its escaped form.
LATEX_SPECIAL: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# The alternation is built from re.escape(k) so the regex metacharacters
# among the keys (backslash, braces, dollar, caret) are matched literally.
_PATTERN: re.Pattern[str] = re.compile(
    "|".join(re.escape(key) for key in LATEX_SPECIAL)
)


def escape_latex(text: str) -> str:
    """Escape LaTeX special characters in a text-mode string.

    Parameters
    ----------
    text : str
        Arbitrary text-mode content, e.g. narrative prose emitted by a
        language model. Must already be a ``str``; callers are responsible
        for decoding bytes.

    Returns
    -------
    str
        A string safe to inject into a LaTeX *text-mode* body, with each of
        the ten special characters replaced by its escaped equivalent.

    Notes
    -----
    A single-pass substitution over the input is used deliberately (see the
    module docstring): sequential ``str.replace`` calls would re-escape the
    characters introduced by earlier replacements and produce corrupt
    output. This routine targets text mode only; it does **not** sanitise
    content intended for math mode, verbatim environments, or file paths.

    Examples
    --------
    >>> escape_latex("100% of AUM in fund_A & B")
    '100\\\\% of AUM in fund\\\\_A \\\\& B'
    >>> escape_latex(r"a backslash \\ and a caret ^")
    'a backslash \\\\textbackslash{} and a caret \\\\textasciicircum{}'
    """
    return _PATTERN.sub(lambda match: LATEX_SPECIAL[match.group()], text)
