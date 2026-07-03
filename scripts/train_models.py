"""
Train FXGuard USD/RWF depreciation-risk models.
Creates 7-day and 14-day models using chronological train/test split.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBClassifier
except ModuleNotFoundError:
    XGBClassifier = None

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "backend" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_COLUMNS: List[str] = [
    "mid_rate",
    "daily_return",
    "return_7d",
    "return_14d",
    "ma_7",
    "ma_14",
    "ma_30",
    "ma_gap",
    "volatility_7d",
    "volatility_14d",
    "volatility_30d",
    "momentum_7d",
    "momentum_14d",
    "spread",
    "spread_pct",
    "depreciation_days_7d",
    "depreciation_days_14d",
]

CLASS_ORDER = ["Low", "Medium", "High"]
CLASS_TO_INT = {label: idx for idx, label in enumerate(CLASS_ORDER)}
INT_TO_CLASS = {idx: label for label, idx in CLASS_TO_INT.items()}


def load_dataset(horizon: int) -> pd.DataFrame:
    filename = f"exchange_rates_model_ready_{horizon}d_4year.csv"
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    label_col = f"risk_label_{horizon}d"
    df = df.dropna(subset=FEATURE_COLUMNS + [label_col]).copy()
    df = df.sort_values("date").reset_index(drop=True)
    return df


def chronological_split(df: pd.DataFrame, train_ratio: float = 0.80):
    split_index = int(len(df) * train_ratio)
    return df.iloc[:split_index].copy(), df.iloc[split_index:].copy()


def class_distribution(labels) -> Dict[str, int]:
    counts = pd.Series(labels).value_counts().to_dict()
    return {label: int(counts.get(label, 0)) for label in CLASS_ORDER}


def probability_metrics(y_true, y_prob) -> Dict:
    if y_prob is None:
        return {}

    y_true_one_hot = pd.get_dummies(pd.Categorical(y_true, categories=CLASS_ORDER)).to_numpy(dtype=float)
    clipped = np.clip(np.asarray(y_prob, dtype=float), 1e-12, 1.0)
    top_probability = clipped.max(axis=1)
    return {
        "log_loss": round(float(log_loss(y_true, clipped, labels=CLASS_ORDER)), 4),
        "brier_multiclass": round(float(np.mean(np.sum((clipped - y_true_one_hot) ** 2, axis=1))), 4),
        "mean_top_probability": round(float(np.mean(top_probability)), 4),
    }


def evaluate(y_true, y_pred, y_prob=None) -> Dict:
    metrics = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 4),
        "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "class_distribution": class_distribution(y_true),
        "confusion_matrix_labels": CLASS_ORDER,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=CLASS_ORDER).tolist(),
        "classification_report": classification_report(y_true, y_pred, zero_division=0, output_dict=True),
    }
    metrics.update(probability_metrics(y_true, y_prob))
    return metrics


def predict_labels_and_probabilities(model, name: str, X):
    if name == "xgboost":
        raw_preds = model.predict(X)
        preds = pd.Series(raw_preds).map(INT_TO_CLASS).to_numpy()
        probs = model.predict_proba(X) if hasattr(model, "predict_proba") else None
        return preds, probs

    preds = model.predict(X)
    probs = None
    if hasattr(model, "predict_proba"):
        raw_probs = model.predict_proba(X)
        probs_by_class = pd.DataFrame(raw_probs, columns=model.classes_)
        probs = probs_by_class.reindex(columns=CLASS_ORDER, fill_value=0.0).to_numpy()
    return preds, probs


def majority_class_baseline(y_train, y_test) -> Dict:
    majority_class = str(pd.Series(y_train).mode().iloc[0])
    preds = np.repeat(majority_class, len(y_test))
    metrics = evaluate(y_test, preds)
    metrics["majority_class"] = majority_class
    return metrics


def evaluation_warnings(train_df: pd.DataFrame, test_df: pd.DataFrame, label_col: str) -> List[str]:
    warnings = []
    train_classes = set(train_df[label_col].dropna())
    test_classes = set(test_df[label_col].dropna())
    missing_test_classes = [label for label in CLASS_ORDER if label not in test_classes]
    missing_train_classes = [label for label in CLASS_ORDER if label not in train_classes]

    if missing_test_classes:
        warnings.append(
            "The chronological test window does not contain these classes: "
            + ", ".join(missing_test_classes)
            + ". Metrics may look overly strong and should be interpreted with caution."
        )
    if missing_train_classes:
        warnings.append(
            "The training window does not contain these classes: "
            + ", ".join(missing_train_classes)
            + ". The model may not learn those risk regimes well."
        )
    return warnings


def rolling_origin_backtest(base_model, name: str, df: pd.DataFrame, label_col: str) -> List[Dict]:
    folds = []
    windows = [(0.60, 0.70), (0.70, 0.80), (0.80, 0.90)]
    for train_end_ratio, test_end_ratio in windows:
        train_end = int(len(df) * train_end_ratio)
        test_end = int(len(df) * test_end_ratio)
        train_df = df.iloc[:train_end].copy()
        test_df = df.iloc[train_end:test_end].copy()
        if train_df.empty or test_df.empty:
            continue

        model = clone(base_model)
        X_train = train_df[FEATURE_COLUMNS]
        y_train = train_df[label_col]
        X_test = test_df[FEATURE_COLUMNS]
        y_test = test_df[label_col]

        if name == "xgboost":
            model.fit(X_train, y_train.map(CLASS_TO_INT))
        else:
            model.fit(X_train, y_train)

        preds, probs = predict_labels_and_probabilities(model, name, X_test)
        folds.append({
            "train_end": str(train_df["date"].max().date()),
            "test_start": str(test_df["date"].min().date()),
            "test_end": str(test_df["date"].max().date()),
            "testing_rows": len(test_df),
            "metrics": evaluate(y_test, preds, probs),
        })
    return folds


def write_evaluation_report(metadata: Dict):
    report_path = ROOT / "reports" / "model_evaluation.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# FXGuard AI Model Evaluation",
        "",
        "This report is generated by `scripts/train_models.py` and summarizes the current validation story for the USD/RWF risk models.",
        "",
    ]

    for key, model_info in metadata["models"].items():
        best_name = model_info["best_model"]
        best_metrics = model_info["metrics"][best_name]
        baseline = model_info["baseline"]["majority_class"]
        lines.extend([
            f"## {model_info['horizon_days']}-day horizon",
            "",
            f"- Best model: `{best_name}`",
            f"- Train window: {model_info['date_range']['start']} to {model_info['date_range']['train_end']}",
            f"- Test window: {model_info['date_range']['test_start']} to {model_info['date_range']['end']}",
            f"- Train class distribution: {model_info['class_distribution']['train']}",
            f"- Test class distribution: {model_info['class_distribution']['test']}",
            f"- Majority baseline: `{baseline['majority_class']}` with F1 macro {baseline['f1_macro']}",
            f"- Best-model F1 macro: {best_metrics['f1_macro']}",
            f"- Best-model balanced accuracy: {best_metrics['balanced_accuracy']}",
        ])
        if "log_loss" in best_metrics:
            lines.append(f"- Best-model log loss: {best_metrics['log_loss']}")
        if "brier_multiclass" in best_metrics:
            lines.append(f"- Best-model multiclass Brier score: {best_metrics['brier_multiclass']}")
        if model_info.get("evaluation_warnings"):
            lines.append("- Evaluation warnings:")
            lines.extend([f"  - {warning}" for warning in model_info["evaluation_warnings"]])
        if model_info.get("skipped_models"):
            lines.append("- Skipped models:")
            lines.extend([f"  - {item['model']}: {item['reason']}" for item in model_info["skipped_models"]])
        lines.append("")
        lines.append("Rolling-origin backtest folds:")
        for fold in model_info.get("rolling_origin_backtest", []):
            lines.append(
                f"- {fold['test_start']} to {fold['test_end']}: "
                f"F1 macro {fold['metrics']['f1_macro']}, "
                f"balanced accuracy {fold['metrics']['balanced_accuracy']}, "
                f"class distribution {fold['metrics']['class_distribution']}"
            )
        lines.append("")

    lines.extend([
        "## Interpretation Notes",
        "",
        "- Chronological testing is used to reduce leakage from future observations into past predictions.",
        "- If a test window contains only one risk class, accuracy can look perfect without proving the model handles all risk regimes.",
        "- Macro F1 and balanced accuracy are reported alongside accuracy because the risk labels may be imbalanced.",
        "- Log loss and multiclass Brier score are included when probabilities are available, because the app displays confidence-like probabilities.",
        "- The model should be retrained and the report regenerated whenever newer BNR exchange-rate data is added.",
        "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")


def train_for_horizon(horizon: int) -> Dict:
    df = load_dataset(horizon)
    label_col = f"risk_label_{horizon}d"
    train_df, test_df = chronological_split(df, 0.80)

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df[label_col]
    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df[label_col]
    y_train_xgb = y_train.map(CLASS_TO_INT)

    models = {
        "logistic_regression": Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42)),
        ]),
        "random_forest": RandomForestClassifier(
            n_estimators=350,
            max_depth=9,
            min_samples_leaf=4,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        ),
    }
    skipped_models = []
    if XGBClassifier is None:
        skipped_models.append({"model": "xgboost", "reason": "xgboost is not installed in this Python environment"})
    else:
        models["xgboost"] = XGBClassifier(
            objective="multi:softprob",
            num_class=len(CLASS_ORDER),
            n_estimators=250,
            learning_rate=0.05,
            max_depth=5,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            random_state=42,
            tree_method="hist",
            eval_metric="mlogloss",
        )

    results: Dict[str, Dict] = {}
    best_name = None
    best_model = None
    best_f1 = -1.0

    for name, model in models.items():
        if name == "xgboost":
            model.fit(X_train, y_train_xgb)
        else:
            model.fit(X_train, y_train)
        preds, probs = predict_labels_and_probabilities(model, name, X_test)
        metrics = evaluate(y_test, preds, probs)
        results[name] = metrics
        if metrics["f1_macro"] > best_f1:
            best_f1 = metrics["f1_macro"]
            best_name = name
            best_model = model

    assert best_model is not None and best_name is not None

    model_path = MODEL_DIR / f"risk_model_{horizon}d.pkl"
    joblib.dump(best_model, model_path)

    latest_row = df.iloc[-1]
    metadata = {
        "horizon_days": horizon,
        "label_column": label_col,
        "feature_columns": FEATURE_COLUMNS,
        "class_order": CLASS_ORDER,
        "best_model": best_name,
        "model_path": str(model_path.relative_to(ROOT)),
        "training_rows": len(train_df),
        "testing_rows": len(test_df),
        "class_distribution": {
            "train": class_distribution(y_train),
            "test": class_distribution(y_test),
        },
        "baseline": {
            "majority_class": majority_class_baseline(y_train, y_test),
        },
        "evaluation_warnings": evaluation_warnings(train_df, test_df, label_col),
        "skipped_models": skipped_models,
        "rolling_origin_backtest": rolling_origin_backtest(best_model, best_name, df, label_col),
        "date_range": {
            "start": str(df["date"].min().date()),
            "end": str(df["date"].max().date()),
            "train_end": str(train_df["date"].max().date()),
            "test_start": str(test_df["date"].min().date()),
        },
        "latest_rate": {
            "date": str(latest_row["date"].date()),
            "currency": str(latest_row["currency"]),
            "mid_rate": round(float(latest_row["mid_rate"]), 4),
        },
        "metrics": results,
    }
    return metadata


def main():
    all_metadata = {"project": "FXGuard AI", "currency_pair": "USD/RWF", "models": {}}
    for horizon in [7, 14]:
        print(f"Training {horizon}-day model...")
        all_metadata["models"][f"{horizon}d"] = train_for_horizon(horizon)

    metadata_path = MODEL_DIR / "model_metadata.json"
    metadata_path.write_text(json.dumps(all_metadata, indent=2), encoding="utf-8")
    write_evaluation_report(all_metadata)
    print(f"Saved metadata: {metadata_path}")
    print(f"Saved report: {ROOT / 'reports' / 'model_evaluation.md'}")
    print("Done.")


if __name__ == "__main__":
    main()
