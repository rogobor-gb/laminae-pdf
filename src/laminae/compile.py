"""Compile a LaTeX source file to PDF.

This module wraps a LaTeX engine as a subprocess. Two properties matter for
use inside long-running or concurrent (e.g. agentic) processes:

* **No global state mutation.** The working directory is passed explicitly
  via ``cwd`` to :func:`subprocess.run`; the parent process's directory is
  never changed with :func:`os.chdir`. The function is therefore reentrant
  and safe under concurrency.
* **Deterministic multi-pass resolution.** Cross-references and the table of
  contents require repeated passes. When ``latexmk`` is available it is
  preferred, as it reruns the engine until references stabilise; otherwise a
  fixed number of engine passes is executed.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

__all__ = ["compile_pdf", "CompilationError"]

#: Map a LaTeX engine name to the corresponding ``latexmk`` selector flag.
_LATEXMK_ENGINE_FLAG: dict[str, str] = {
    "xelatex": "-xelatex",
    "lualatex": "-lualatex",
    "pdflatex": "-pdf",
}


class CompilationError(RuntimeError):
    """Raised when the LaTeX engine exits with a non-zero status."""


def _run(command: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.splitlines()[-lines:])


def compile_pdf(
    tex_path: Path | str,
    *,
    engine: str = "xelatex",
    passes: int = 2,
    timeout: int = 180,
    prefer_latexmk: bool = True,
) -> Path:
    """Compile a ``.tex`` file to PDF and return the output path.

    Parameters
    ----------
    tex_path : pathlib.Path or str
        Path to the ``.tex`` file. Compilation runs with the file's parent
        directory as the working directory, so relative asset references
        (e.g. ``contents/figure.png``) resolve correctly.
    engine : {"xelatex", "lualatex", "pdflatex"}, optional
        LaTeX engine. ``xelatex`` is the default because the shipped
        templates use ``fontspec`` (system/OpenType fonts).
    passes : int, optional
        Number of engine passes in the fallback path (used only when
        ``latexmk`` is unavailable or ``prefer_latexmk`` is ``False``).
    timeout : int, optional
        Per-invocation timeout in seconds.
    prefer_latexmk : bool, optional
        Use ``latexmk`` when present (recommended); it handles rerun logic.

    Returns
    -------
    pathlib.Path
        Path to the generated PDF (``tex_path`` with a ``.pdf`` suffix).

    Raises
    ------
    ValueError
        If ``engine`` is not recognised.
    FileNotFoundError
        If ``tex_path`` does not exist.
    CompilationError
        If the engine exits non-zero or the PDF is not produced.
    subprocess.TimeoutExpired
        If an invocation exceeds ``timeout``.
    """
    if engine not in _LATEXMK_ENGINE_FLAG:
        raise ValueError(
            f"unknown engine {engine!r}; choose from {sorted(_LATEXMK_ENGINE_FLAG)}"
        )

    tex_path = Path(tex_path)
    if not tex_path.is_file():
        raise FileNotFoundError(f"tex file not found: {tex_path}")

    workdir = tex_path.parent
    tex_name = tex_path.name
    pdf_path = tex_path.with_suffix(".pdf")

    use_latexmk = prefer_latexmk and shutil.which("latexmk") is not None
    if use_latexmk:
        command = [
            "latexmk",
            _LATEXMK_ENGINE_FLAG[engine],
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            tex_name,
        ]
        result = _run(command, workdir, timeout)
        if result.returncode != 0:
            raise CompilationError(
                f"latexmk failed for {tex_name}:\n{_tail(result.stdout)}"
            )
    else:
        command = ["-interaction=nonstopmode", "-halt-on-error", tex_name]
        for _ in range(max(1, passes)):
            result = _run([engine, *command], workdir, timeout)
            if result.returncode != 0:
                raise CompilationError(
                    f"{engine} failed for {tex_name}:\n{_tail(result.stdout)}"
                )

    if not pdf_path.is_file():
        raise CompilationError(f"PDF not produced: expected {pdf_path}")
    return pdf_path
