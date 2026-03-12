#dashboard.py

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import seaborn as sns


def plot_confusion_matrix(cm, save_path: Path | None = None) -> None:
    """Plot confusion matrix heatmap and optionally save it to disk."""
    plt.figure(figsize=(6, 5))
    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["REAL", "FAKE"],
        yticklabels=["REAL", "FAKE"],
    )
    plt.title("Confusion Matrix")
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.tight_layout()

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150)


def plot_metrics(metrics_dict: dict[str, float], save_path: Path | None = None) -> None:
    """Plot evaluation metrics as a bar chart and optionally save it to disk."""
    labels = ["Accuracy", "Precision", "Recall", "F1 Score"]
    values = [
        metrics_dict.get("accuracy", 0.0),
        metrics_dict.get("precision", 0.0),
        metrics_dict.get("recall", 0.0),
        metrics_dict.get("f1", 0.0),
    ]

    plt.figure(figsize=(7, 5))
    bars = plt.bar(labels, values, color=["#4C78A8", "#72B7B2", "#54A24B", "#E45756"])
    plt.ylim(0, 1)
    plt.title("Model Evaluation Metrics")
    plt.ylabel("Score")

    for bar, value in zip(bars, values):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.02,
            f"{value:.2f}",
            ha="center",
            va="bottom",
        )

    plt.tight_layout()

    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150)
