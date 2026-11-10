"""Render the checked-in sanitized memory evidence; matplotlib is an offline QA tool."""

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".runtime/matplotlib"))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads((root / "docs/memory-reliability-evidence.json").read_text(encoding="utf-8"))
    names = ["large_geometry", "numeric_response_concurrent", "excessive_geometry",
             "long_rec_rejected", "large_response_rejected"]
    labels = ["256 DET regions", "Numeric REC\n4 pipelines", "1001 regions\nrejected",
              "100001 chars\nrejected", "65 MiB body\nrejected"]
    groups = [("baseline", "Before, 12.8 MP (swap allowed)", "#64748b"), ("final_matched_swap", "Final, 12.8 MP (same swap limit)", "#2563eb"),
              ("final_candidate_40mp", "Final candidate, 40 MP (no swap)", "#059669")]
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), constrained_layout=True)
    for i, (key, title, color) in enumerate(groups):
        phases = evidence["groups"][key]["phases"]
        x = [j + (i - 1) * .25 for j in range(len(names))]
        axes[0].bar(x, [phases[n]["sampled_peak_range"][1] / 1e6 for n in names], width=.24, color=color, label=title)
        axes[1].bar(x, [phases[n]["median_seconds"] for n in names], width=.24, color=color, label=title)
    axes[0].axhline(512, color="#b91c1c", linestyle="--", label="Container limit: 512 MB")
    axes[0].axhline(409.6, color="#a16207", linestyle=":", label="Proposed 20% free target")
    axes[0].set_ylabel("Worst sampled cgroup usage (decimal MB)")
    axes[0].set_ylim(0, 560)
    axes[0].legend(fontsize=8, ncol=2)
    axes[0].set_title("Matched before/after at 12.8 MP; separate 40 MP final workload. 1 CPU, 3 trials/group")
    axes[1].set_ylabel("Median job latency (seconds)")
    axes[1].set_title("Correct results retained; numeric parsing trades CPU time for lower heap use")
    for ax in axes:
        ax.set_xticks(range(len(names)), labels)
        ax.grid(axis="y", alpha=.15)
        ax.set_axisbelow(True)
    fig.savefig(root / "docs/memory-reliability-comparison.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for i, key in enumerate(("before", "after-spool")):
        probe = evidence["transport"][key]
        axes[0].bar(i, max(probe["kernel_peaks"]) / 1e6, color=["#64748b", "#2563eb"][i])
        axes[1].bar(i, probe["heap_peak"] / 1e6, color=["#64748b", "#2563eb"][i])
    for ax in axes:
        ax.set_xticks([0, 1], ["Before", "After"])
        ax.set_ylabel("Decimal MB")
        ax.grid(axis="y", alpha=.15)
        ax.set_axisbelow(True)
    axes[0].set_title("Transport probe: worst kernel peak\n4 x 13.32 MB responses, 3 fresh containers")
    axes[1].set_title("Separate tracemalloc run: peak Python heap\n4 x 3.33 MB responses; instrumentation enabled")
    fig.savefig(root / "docs/memory-reliability-allocations.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
