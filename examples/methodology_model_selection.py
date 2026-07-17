"""Methodology deck: parameter selection in a stability region.

A worked, self-contained example that turns a quantitative *methodology* — the
"rank-persistence" rule for selecting a strategy parameter :math:`\\theta^*`
under non-stationarity — into a slide deck, using every part of the ``laminae``
trust boundary:

* ``ProseSlide``      narrative authored as *data* and escaped at the boundary
                      (the path a language model would use);
* ``RawLatexSlide``   the mathematics, inserted verbatim by *trusted* code
                      (a model can never emit this — it is off the plan schema);
* ``FigureSlide``     figures synthesised by the deterministic code below;
* ``TableSlide``      CSVs read at render time and typeset as booktabs tables.

The same ``Report`` is rendered under all three shipped templates
(``clean``, ``accent``, ``ember``), producing three PDFs, so the deck doubles as
a visual diff of the templates.

Run
---
    python examples/methodology_model_selection.py            # all 3 templates
    python examples/methodology_model_selection.py accent     # just one

Requires ``pydantic`` and (for the generated figures) ``numpy`` + ``matplotlib``;
needs a LaTeX engine (XeLaTeX) on PATH to produce the PDFs. The ``ember``
template additionally needs the system fonts Palatino, Helvetica and Monaco.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from laminae import (  # noqa: E402
    FigureSlide,
    ProseSlide,
    RawLatexSlide,
    Report,
    SectionSlide,
    TableSlide,
    compile_pdf,
    render_to_file,
)

# Written under examples/output/, which .gitignore already excludes.
OUT_BASE = Path(__file__).resolve().parent / "output" / "methodology"
TEMPLATES = ("clean", "accent", "ember")

# --------------------------------------------------------------------------- #
# A synthetic — but internally consistent — utility landscape.
#
# The parameter space is a 2-D grid Theta = {(t1, t2)}. Each time window W_k
# has its own utility surface U_k: a broad shared plateau (the genuinely robust
# region) that drifts slightly window-to-window (non-stationarity), plus a
# per-window "decoy" spike far from the plateau (an isolated high performer
# that the connectivity filter must reject) and low-amplitude noise. Every
# figure below is derived from this one model, so the story stays coherent.
# --------------------------------------------------------------------------- #
GRID_N = 41
AXIS = np.linspace(0.0, 1.0, GRID_N)
XX, YY = np.meshgrid(AXIS, AXIS)
PLATEAU = (0.62, 0.42)  # centre of the true robust region
ALPHA = 0.10  # top-alpha threshold
TAU = 0.60  # majority-vote threshold
N_WINDOWS = 5


def _gaussian(cx: float, cy: float, sigma: float) -> np.ndarray:
    return np.exp(-((XX - cx) ** 2 + (YY - cy) ** 2) / (2.0 * sigma**2))


def _utility(window: int, rng: np.random.Generator) -> np.ndarray:
    """Utility surface for one window: plateau + drift + decoy + noise."""
    drift = 0.03 * np.sin(window)  # small, window-specific plateau drift
    cx, cy = PLATEAU[0] + drift, PLATEAU[1] - 0.02 * window / N_WINDOWS
    surface = _gaussian(cx, cy, 0.16)
    # An isolated decoy peak somewhere far from the plateau.
    dx, dy = rng.uniform(0.05, 0.30), rng.uniform(0.70, 0.95)
    surface += 0.85 * _gaussian(dx, dy, 0.045)
    surface += rng.normal(0.0, 0.045, surface.shape)
    return surface


def _rank_percentile(utility: np.ndarray) -> np.ndarray:
    """Map a utility surface to rank percentiles in (0, 1]; low = good."""
    flat = utility.ravel()
    order = flat.argsort()[::-1]  # best utility first
    ranks = np.empty(flat.size, dtype=float)
    ranks[order] = np.arange(1, flat.size + 1)
    return (ranks / flat.size).reshape(utility.shape)


def _largest_connected_component(mask: np.ndarray) -> np.ndarray:
    """Return the largest 8-connected component of a boolean grid mask."""
    visited = np.zeros_like(mask, dtype=bool)
    best: np.ndarray = np.zeros_like(mask, dtype=bool)
    ny, nx = mask.shape
    for i in range(ny):
        for j in range(nx):
            if not mask[i, j] or visited[i, j]:
                continue
            component = []
            queue = deque([(i, j)])
            visited[i, j] = True
            while queue:
                y, x = queue.popleft()
                component.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if (
                            0 <= yy < ny
                            and 0 <= xx < nx
                            and mask[yy, xx]
                            and not visited[yy, xx]
                        ):
                            visited[yy, xx] = True
                            queue.append((yy, xx))
            if len(component) > int(best.sum()):
                best = np.zeros_like(mask, dtype=bool)
                for y, x in component:
                    best[y, x] = True
    return best


def _windows() -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Rank surfaces and per-window LCC regions for every window."""
    rng = np.random.default_rng(7)
    ranks = [_rank_percentile(_utility(k, rng)) for k in range(N_WINDOWS)]
    regions = [_largest_connected_component(r <= ALPHA) for r in ranks]
    return ranks, regions


# --------------------------------------------------------------------------- #
# Figures — each saved into <out>/contents and referenced by a FigureSlide.
# --------------------------------------------------------------------------- #
def _fig_rank_surfaces(ranks: list[np.ndarray], path: Path) -> None:
    """A row of rank-percentile heatmaps: shared plateau, drifting per window."""
    show = [0, 2, 4]
    fig, axes = plt.subplots(1, len(show), figsize=(9.2, 3.3), constrained_layout=True)
    im = None
    for ax, k in zip(axes, show):
        im = ax.imshow(
            ranks[k],
            origin="lower",
            extent=(0, 1, 0, 1),
            cmap="viridis_r",
            vmin=0.0,
            vmax=1.0,
        )
        ax.contour(XX, YY, ranks[k], levels=[ALPHA], colors="white", linewidths=1.4)
        ax.set_title(f"window $W_{k}$", fontsize=11)
        ax.set_xlabel(r"$\theta_1$")
        ax.set_xticks([0, 0.5, 1])
        ax.set_yticks([0, 0.5, 1])
    axes[0].set_ylabel(r"$\theta_2$")
    cbar = fig.colorbar(im, ax=axes, shrink=0.85, pad=0.02)
    cbar.set_label(r"rank percentile $R_k(\theta)$  (low = good)")
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _fig_region_construction(
    ranks: list[np.ndarray], regions: list[np.ndarray], path: Path
) -> None:
    """Top-alpha set (with decoys) vs the surviving largest component."""
    k = 0
    top_alpha = ranks[k] <= ALPHA
    lcc = regions[k]
    discarded = top_alpha & ~lcc

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.0), constrained_layout=True)
    for ax in (ax1, ax2):
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal")
        ax.set_xlabel(r"$\theta_1$")
    ax1.set_ylabel(r"$\theta_2$")

    ax1.scatter(XX[top_alpha], YY[top_alpha], s=16, c="#5B2A86")
    ax1.set_title(
        r"top-$\alpha$ set $\Theta_k^{\alpha}$  ($R_k\leq\alpha$)", fontsize=11
    )

    ax2.scatter(
        XX[discarded],
        YY[discarded],
        s=16,
        c="#B0B0B0",
        label="isolated (discarded)",
    )
    ax2.scatter(
        XX[lcc],
        YY[lcc],
        s=16,
        c="#2E8728",
        label=r"$\hat\Theta_k=\mathrm{LCC}$",
    )
    ax2.set_title("after connectivity filter", fontsize=11)
    ax2.legend(loc="upper right", fontsize=8, framealpha=0.9)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _fig_majority_vote(regions: list[np.ndarray], path: Path) -> tuple[float, float]:
    """Majority-vote score surface, aggregated region and the medoid theta*."""
    score = np.mean(regions, axis=0)  # fraction of windows keeping theta
    aggregated = score >= TAU

    # Medoid: the element of the aggregated region minimising total distance.
    idx = np.argwhere(aggregated)  # (row=i -> theta2, col=j -> theta1)
    pts = np.column_stack([AXIS[idx[:, 1]], AXIS[idx[:, 0]]])
    dmat = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    medoid = pts[dmat.sum(1).argmin()]

    fig, ax = plt.subplots(figsize=(6.4, 4.6), constrained_layout=True)
    im = ax.imshow(
        score,
        origin="lower",
        extent=(0, 1, 0, 1),
        cmap="YlOrBr",
        vmin=0.0,
        vmax=1.0,
    )
    ax.contour(
        XX,
        YY,
        score,
        levels=[TAU],
        colors="#8E1B1B",
        linewidths=1.8,
    )
    ax.plot(
        medoid[0],
        medoid[1],
        marker="*",
        markersize=20,
        color="#8E1B1B",
        markeredgecolor="white",
        markeredgewidth=1.2,
        linestyle="none",
        label=r"medoid $\theta^{*}$",
    )
    ax.annotate(
        rf"$\theta^{{*}}\approx({medoid[0]:.2f},\,{medoid[1]:.2f})$",
        xy=(medoid[0], medoid[1]),
        xytext=(medoid[0] + 0.06, medoid[1] - 0.18),
        fontsize=10,
        color="#8E1B1B",
        arrowprops=dict(arrowstyle="->", color="#8E1B1B"),
    )
    ax.set_xlabel(r"$\theta_1$")
    ax.set_ylabel(r"$\theta_2$")
    ax.set_title(r"majority-vote score $\mathrm{Score}(\theta)$", fontsize=11)
    ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
    cbar = fig.colorbar(im, ax=ax, shrink=0.9, pad=0.02)
    cbar.set_label(r"fraction of windows retaining $\theta$")
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return float(medoid[0]), float(medoid[1])


def _fig_timeline(path: Path) -> None:
    """The held-out test slice: W_0..W_{K-2} train, W_{K-1} held out."""
    fig, ax = plt.subplots(figsize=(9.2, 2.4), constrained_layout=True)
    ax.set_xlim(-0.3, N_WINDOWS + 0.3)
    ax.set_ylim(0, 1)
    ax.axis("off")
    labels = [f"$W_{k}$" for k in range(N_WINDOWS - 1)] + [f"$W_{{{N_WINDOWS - 1}}}$"]
    for k, label in enumerate(labels):
        held_out = k == N_WINDOWS - 1
        ax.add_patch(
            plt.Rectangle(
                (k + 0.08, 0.32),
                0.84,
                0.36,
                facecolor="#FBE9E7" if held_out else "#EDE7F3",
                edgecolor="#8E1B1B" if held_out else "#5B2A86",
                linewidth=1.6,
                linestyle="--" if held_out else "-",
                zorder=2,
            )
        )
        ax.text(k + 0.5, 0.5, label, ha="center", va="center", fontsize=12, zorder=3)
    # Training bracket.
    ax.add_patch(
        plt.Rectangle(
            (0.02, 0.24),
            N_WINDOWS - 1 + 0.04,
            0.52,
            facecolor="none",
            edgecolor="#5B2A86",
            linewidth=1.0,
            zorder=1,
        )
    )
    ax.text(
        (N_WINDOWS - 1) / 2,
        0.85,
        "Training (region + $\\theta^{*}$)",
        ha="center",
        va="center",
        fontsize=11,
        color="#5B2A86",
    )
    ax.text(
        N_WINDOWS - 0.5,
        0.85,
        "Test (held out)",
        ha="center",
        va="center",
        fontsize=11,
        color="#8E1B1B",
        style="italic",
    )
    ax.annotate(
        "no leakage",
        xy=(N_WINDOWS - 1 + 0.06, 0.5),
        xytext=(N_WINDOWS - 1 - 0.6, 0.12),
        fontsize=8,
        color="#8E1B1B",
        arrowprops=dict(arrowstyle="->", color="#8E1B1B"),
    )
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _write_assets(contents: Path) -> None:
    """Generate every figure and CSV under ``contents``."""
    contents.mkdir(parents=True, exist_ok=True)
    ranks, regions = _windows()
    _fig_rank_surfaces(ranks, contents / "rank_surfaces.png")
    _fig_region_construction(ranks, regions, contents / "region_construction.png")
    _fig_majority_vote(regions, contents / "majority_vote.png")
    _fig_timeline(contents / "timeline.png")

    (contents / "product_utility.csv").write_text(
        "Product,Utility U_k(theta)\n"
        "IT — sparse index tracking,-TE_k(theta) - lambda * Turnover_k(theta)\n"
        "IT+ — index tracking plus,-|mean ExcessRet_k(theta)|\n",
        encoding="utf-8",
    )
    (contents / "persistence.csv").write_text(
        "Pi(i->j),W1,W2,W3,W4\n"
        "W0,0.86,0.79,0.74,0.71\n"
        "W1,—,0.83,0.77,0.72\n"
        "W2,—,—,0.81,0.76\n"
        "W3,—,—,—,0.80\n",
        encoding="utf-8",
    )
    (contents / "failure_modes.csv").write_text(
        "Failure,Diagnosis,Action\n"
        "No connected region,Noise-dominated landscape,Simplify model; shrink Theta\n"
        "No persistence,Overfitting or fast regime change,Shrink Theta or shorten gap\n"
        "Low Jaccard overlap,Landscape drifting,Introduce recency weighting\n"
        "Fragmented region,Multiple parameter sub-families,Split components; regime-switch\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# The report. Prose is escaped (safe path); the mathematics rides the trusted
# RawLatexSlide hatch — a language model could never emit it.
# --------------------------------------------------------------------------- #
def _raw(title: str, body: str) -> RawLatexSlide:
    """A trusted math frame: a frametitle followed by verbatim LaTeX."""
    return RawLatexSlide(body=f"\\frametitle{{{title}}}\n{body}")


def build_report(template: str) -> Report:
    """Assemble the methodology deck for one template.

    Note the division of labour that ``laminae`` enforces: *titles and captions
    are escaped data*, so they carry plain words, never LaTeX — every symbol and
    formula lives in a trusted ``RawLatexSlide`` (or is drawn into the figure
    itself). Putting ``$\\theta^*$`` in a caption would render the literal
    characters, which is exactly the injection-proofing the library is for.
    """
    return Report(
        title="Selecting a Parameter in a Stability Region",
        author="G. Breschi",
        institution="Strategy Research — Pipeline step 5.2",
        template=template,  # type: ignore[arg-type]
        include_toc=True,
        slides=[
            # ---- The problem ---------------------------------------------- #
            SectionSlide(title="The problem"),
            ProseSlide(
                title="Validation under non-stationarity",
                body=(
                    "Markets are non-stationary and we have one history only. "
                    "Evaluation needs long windows (5+ years each) with imbalanced "
                    "regimes, which collapses validation to a single in-sample vs "
                    "out-of-sample split — and the result then hinges on where the "
                    "cut-off date happens to fall. We replace that one split with "
                    "several randomised period slices."
                ),
                block="alert",
                block_title="One history, shifting regimes",
            ),
            _raw(
                "Naive optimisation is unsound",
                "Optimising utility on a fixed window,\n"
                "\\[ \\theta^* = \\arg\\max_{\\theta\\in\\Theta} "
                "U(\\theta;\\,\\mathcal{D}), \\]\n"
                "has no stable out-of-sample meaning: "
                "$U_t(\\theta)\\neq U_{t'}(\\theta)$ across periods, so a level "
                "(or a level distribution) does not transfer. The argmax merely "
                "identifies the strategy best suited to the dominant historical "
                "regime.",
            ),
            ProseSlide(
                title="The reframe: rank persistence",
                body=(
                    "Select the parameter in a region that yields good results "
                    "across many time windows — not the parameter that is best in "
                    "any single window. The target is rank persistence, not utility "
                    "optimisation."
                ),
                block="example",
                block_title="Change of mindset",
            ),
            TableSlide(
                title="Product-specific utility",
                path="product_utility.csv",
                first_col_is_index=True,
            ),
            # ---- Rank surface & regions ----------------------------------- #
            SectionSlide(title="Rank surface and regions"),
            _raw(
                "Rank normalisation",
                "Map utility to a rank percentile, killing level "
                "non-stationarity:\n"
                "\\[ R_k(\\theta) := "
                "\\frac{\\operatorname{rank}\\bigl(U_k(\\theta),\\,"
                "\\{U_k(\\theta'):\\theta'\\in\\Theta\\}\\bigr)}{|\\Theta|} "
                "\\;\\in\\;(0,1]. \\]\n"
                "Low $R_k(\\theta)$ is good. The map is invariant to affine "
                "shifts of $U_k$, so rank surfaces are comparable across windows "
                "and regimes.",
            ),
            FigureSlide(
                title="Rank surfaces across windows",
                path="rank_surfaces.png",
                caption=(
                    "The same plateau stays near the top of every window (the "
                    "white contour marks the best-ranked set); its location drifts "
                    "window to window — the non-stationarity that rank "
                    "normalisation absorbs."
                ),
            ),
            _raw(
                "Region construction (per window)",
                "\\textbf{Top-$\\alpha$ set.}\\quad "
                "$\\Theta_k^{\\alpha} := \\{\\theta\\in\\Theta : "
                "R_k(\\theta)\\le\\alpha\\}$, \\; $\\alpha\\in[0.05,0.15]$.\n\n"
                "\\medskip\n"
                "\\textbf{Connectivity filter.}\\quad On a graph over "
                "$\\Theta_k^{\\alpha}$ (edge iff $d(\\theta,\\theta')\\le"
                "\\varepsilon$), keep the largest connected component "
                "$\\hat\\Theta_k = \\operatorname{LCC}(G_k(\\varepsilon))$. "
                "Isolated high performers are noise and are discarded.\n\n"
                "\\medskip\n"
                "\\textbf{Local flatness.}\\quad "
                "$\\sigma^2_{\\mathrm{local}}(\\theta) = "
                "\\frac{1}{|\\mathcal{N}(\\theta)|}\\sum_{\\theta'\\in"
                "\\mathcal{N}(\\theta)}\\bigl(R_k(\\theta)-R_k(\\theta')\\bigr)^2$ "
                "— small on a plateau.",
            ),
            FigureSlide(
                title="Top-alpha set and the connectivity filter",
                path="region_construction.png",
                caption=(
                    "The connectivity filter keeps the largest connected "
                    "component and rejects isolated high performers as noise "
                    "artefacts."
                ),
            ),
            # ---- Aggregation & selection ---------------------------------- #
            SectionSlide(title="Aggregation and selection"),
            _raw(
                "Aggregation: majority vote",
                "The naive intersection $\\bigcap_k \\hat\\Theta_k$ vanishes as "
                "$K$ grows. Use the majority-vote score\n"
                "\\[ \\mathrm{Score}(\\theta) := "
                "\\frac{1}{K}\\sum_{k=1}^{K}\\mathbf{1}\\{\\theta\\in"
                "\\hat\\Theta_k\\}, \\qquad "
                "\\hat\\Theta(\\tau) := \\{\\theta : "
                "\\mathrm{Score}(\\theta)\\ge\\tau\\}. \\]\n"
                "Set $\\tau$ so the expected number of false positives is "
                "$\\le 1$:\n"
                "\\[ \\tau^* := \\min\\Bigl\\{\\tau : |\\Theta|\\cdot"
                "\\mathbb{P}\\bigl(\\mathrm{Binomial}(K,\\alpha)\\ge\\tau K"
                "\\bigr)\\le 1\\Bigr\\}. \\]",
            ),
            FigureSlide(
                title="Majority-vote region and the medoid",
                path="majority_vote.png",
                caption=(
                    "The dark contour is the aggregated region; the star marks "
                    "the medoid — the most central point of the most stable "
                    "sub-region."
                ),
            ),
            _raw(
                "Representative parameter: the medoid",
                "Restrict to the flattest quartile $\\hat\\Theta_{\\mathrm{flat}} "
                "= \\{\\theta\\in\\hat\\Theta(\\tau): "
                "\\sigma^2_{\\mathrm{local}}(\\theta)\\le q_{0.25}\\}$ and take "
                "the medoid\n"
                "\\[ \\theta^* = \\arg\\min_{\\theta\\in"
                "\\hat\\Theta_{\\mathrm{flat}}}\\;\\sum_{\\theta'\\in"
                "\\hat\\Theta_{\\mathrm{flat}}} d(\\theta,\\theta'). \\]\n"
                "The most central element of the most stable sub-region — a "
                "geometric criterion with no within-region utility optimisation.",
            ),
            # ---- Held-out validation -------------------------------------- #
            SectionSlide(title="Held-out validation"),
            FigureSlide(
                title="The held-out test slice",
                path="timeline.png",
                caption=(
                    "The region and the representative parameter are built on the "
                    "first windows only; the final window is untouched until a "
                    "single held-out check."
                ),
            ),
            _raw(
                "Forward persistence and temporal stability",
                "\\textbf{Persistence.}\\quad For $j>i$,\n"
                "\\[ \\Pi_{i\\to j} := \\frac{1}{|\\hat\\Theta_i|}"
                "\\sum_{\\theta\\in\\hat\\Theta_i}\\mathbf{1}\\{R_j(\\theta)\\le"
                "\\beta\\}\\;\\ge\\;p, \\quad \\beta\\in[0.2,0.3],\\; "
                "p\\in[0.7,0.8]. \\]\n"
                "\\textbf{Temporal stability.}\\quad For consecutive windows,\n"
                "\\[ J_{k,k+1} := \\frac{|\\hat\\Theta_k\\cap\\hat\\Theta_{k+1}|}"
                "{|\\hat\\Theta_k\\cup\\hat\\Theta_{k+1}|}\\;\\ge\\;\\gamma, "
                "\\quad \\gamma\\in[0.4,0.6]. \\]\n"
                "A low Jaccard $J$ means the landscape drifts faster than the "
                "window resolves.",
            ),
            TableSlide(
                title="Forward-persistence table",
                path="persistence.csv",
                first_col_is_index=True,
            ),
            # ---- Diagnostics ---------------------------------------------- #
            SectionSlide(title="Diagnostics and output"),
            TableSlide(title="Failure modes", path="failure_modes.csv"),
            ProseSlide(
                title="What 5.2 outputs",
                body=(
                    "The deliverable is not merely the parameter but the whole "
                    "selection rule f: history -> theta*, encoding the windows, "
                    "the thresholds (alpha, beta, gamma, tau, p), the metric and "
                    "the utility. That rule — held fixed, never tuned in-sample — "
                    "is the object of validation, together with the region "
                    "theta-hat(tau) recorded for later sensitivity analysis."
                ),
                block="block",
                block_title="The selection rule is the artefact",
            ),
        ],
    )


def build_one(template: str) -> Path:
    """Render and compile the deck for a single template."""
    out_dir = OUT_BASE / template
    _write_assets(out_dir / "contents")
    report = build_report(template)
    tex_path = render_to_file(report, out_dir, filename=f"methodology_{template}.tex")
    pdf_path = compile_pdf(tex_path, engine="xelatex")
    return pdf_path


def main() -> None:
    requested = sys.argv[1:] or list(TEMPLATES)
    for template in requested:
        if template not in TEMPLATES:
            print(f"skip {template!r}: not one of {TEMPLATES}")
            continue
        try:
            pdf_path = build_one(template)
            print(f"[{template:>6}] {pdf_path}")
        except Exception as exc:  # keep going so the other templates still build
            print(f"[{template:>6}] FAILED: {exc}")


if __name__ == "__main__":
    main()
