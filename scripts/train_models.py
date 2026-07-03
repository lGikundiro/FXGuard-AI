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
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

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


def evaluate(y_true, y_pred) -> Dict:
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "confusion_matrix_labels": CLASS_ORDER,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=CLASS_ORDER).tolist(),
        "classification_report": classification_report(y_true, y_pred, zero_division=0, output_dict=True),
    }


def train_for_horizon(horizon: int) -> Dict:
    df = load_dataset(horizon)
    label_col = f"risk_label_{horizon}d"
    train_df, test_df = chronological_split(df, 0.80)

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df[label_col]
    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df[label_col]

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
        "xgboost": XGBClassifier(
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
        ),
    }

    results: Dict[str, Dict] = {}
    best_name = None
    best_model = None
    best_f1 = -1.0

    for name, model in models.items():
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        metrics = evaluate(y_test, preds)
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
    print(f"Saved metadata: {metadata_path}")
    print("Done.")


if __name__ == "__main__":
    main()
