from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns


def set_chart_style() -> None:
    """Apply a clean default style for notebook charts."""
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams["figure.figsize"] = (10, 5)
    plt.rcParams["axes.titleweight"] = "bold"


def save_figure(filename: str, output_dir: str | Path = "../outputs/figures") -> Path:
    """Save the current Matplotlib figure and return the written path."""
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    plt.savefig(target_path, bbox_inches="tight", dpi=150)
    return target_path
