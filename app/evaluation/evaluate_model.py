#evaluate_model.py

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from matplotlib import pyplot as plt
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dashboard import plot_confusion_matrix, plot_metrics


def predict_label(text: str) -> str:
    """Predict FAKE/REAL label using the same threshold as the verdict engine (FAKE_HIGH = 0.62)."""
    from app.services.nlp_service import analyze_text

    result = analyze_text(text)
    fake_score = float(result.get("fake_score", 0.0))

    return "FAKE" if fake_score >= 0.62 else "REAL"


def save_report(accuracy, precision, recall, f1, cm):
    """Save evaluation metrics to a text report in the project root."""
    with open("evaluation_report.txt", "w") as f:
        f.write("===== MODEL EVALUATION =====\n")
        f.write(f"Accuracy: {accuracy:.2f}\n")
        f.write(f"Precision: {precision:.2f}\n")
        f.write(f"Recall: {recall:.2f}\n")
        f.write(f"F1-score: {f1:.2f}\n\n")
        f.write("Confusion Matrix:\n")
        f.write(str(cm))


def evaluate(csv_path: Path, save: bool = False) -> None:
    """Load dataset, run model predictions, and print evaluation metrics."""
    if not csv_path.exists():
        print(f"Error: file not found: {csv_path}")
        sys.exit(1)

    df = pd.read_csv(csv_path)

    required_columns = {"text", "label"}
    if not required_columns.issubset(df.columns):
        missing = required_columns - set(df.columns)
        print(f"Error: missing required columns: {', '.join(sorted(missing))}")
        sys.exit(1)

    df = df.copy()
    df["label"] = df["label"].astype(str).str.strip().str.upper()
    df = df[df["label"].isin(["FAKE", "REAL"])].dropna(subset=["text", "label"])

    if df.empty:
        print("Error: no valid rows found after filtering labels/text.")
        sys.exit(1)

    y_true = df["label"].tolist()
    y_pred = [predict_label(text) for text in df["text"].astype(str).tolist()]

    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, pos_label="FAKE", zero_division=0)
    recall = recall_score(y_true, y_pred, pos_label="FAKE", zero_division=0)
    f1 = f1_score(y_true, y_pred, pos_label="FAKE", zero_division=0)

    cm = confusion_matrix(y_true, y_pred, labels=["REAL", "FAKE"])
    metrics = {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }

    print("===== MODEL EVALUATION =====")
    print(f"Accuracy: {accuracy:.2f}")
    print(f"Precision: {precision:.2f}")
    print(f"Recall: {recall:.2f}")
    print(f"F1-score: {f1:.2f}")
    print("Confusion Matrix:")
    print(cm)
    save_report(accuracy, precision, recall, f1, cm)

    metrics_path = None
    confusion_path = None
    if save:
        output_dir = Path("evaluation_results")
        metrics_path = output_dir / "metrics_chart.png"
        confusion_path = output_dir / "confusion_matrix.png"

    plot_metrics(metrics, save_path=metrics_path)
    plot_confusion_matrix(cm, save_path=confusion_path)

    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate fake news model on a labeled CSV dataset."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="evaluation_data.csv",
        help="Path to CSV file containing 'text' and 'label' columns.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save charts to evaluation_results/ in addition to displaying them.",
    )
    args = parser.parse_args()

    evaluate(Path(args.csv_path), save=args.save)


if __name__ == "__main__":
    main()