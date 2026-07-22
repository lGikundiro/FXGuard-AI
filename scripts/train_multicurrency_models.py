"""Train separate 7-day and 14-day risk classifiers for each supported currency."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.app.modeling import EncodedTargetClassifier


DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "backend" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

CURRENCIES = ("USD", "EUR", "KES")
CLASS_ORDER = ("Low", "Medium", "High")
FEATURE_COLUMNS = [
    "mid_rate", "daily_return", "return_7d", "return_14d", "ma_7", "ma_14", "ma_30",
    "ma_gap", "volatility_7d", "volatility_14d", "volatility_30d", "momentum_7d",
    "momentum_14d", "spread", "spread_pct", "depreciation_days_7d", "depreciation_days_14d",
]


def candidates() -> dict:
    return {
        "logistic_regression": Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        max_iter=2500,
                        class_weight="balanced",
                        random_state=42,
                    ),
                ),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=180,
            max_depth=10,
            min_samples_leaf=4,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        ),
        "xgboost": EncodedTargetClassifier(
            XGBClassifier(
                objective="multi:softprob",
                num_class=len(CLASS_ORDER),
                n_estimators=250,
                learning_rate=0.05,
                max_depth=5,
                subsample=0.9,
                colsample_bytree=0.9,
                reg_lambda=1.0,
                random_state=42,
                n_jobs=-1,
                tree_method="hist",
                eval_metric="mlogloss",
            ),
            classes=CLASS_ORDER,
        ),
    }


def metrics(y_true, y_pred) -> dict:
    balanced_accuracy = None
    if pd.Series(y_true).nunique() > 1:
        balanced_accuracy = round(float(balanced_accuracy_score(y_true, y_pred)), 4)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "balanced_accuracy": balanced_accuracy,
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
    }


def main() -> None:
    data_metadata = json.loads((DATA_DIR / "multicurrency_data_metadata.json").read_text(encoding="utf-8"))
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "currencies": list(CURRENCIES),
        "data": data_metadata,
        "models": {},
    }

    for currency in CURRENCIES:
        output["models"][currency] = {}
        for horizon in (7, 14):
            dataset = pd.read_csv(
                DATA_DIR / f"multicurrency_model_ready_{horizon}d.csv",
                parse_dates=["date"],
            )
            dataset = dataset.loc[dataset["currency"] == currency].sort_values("date").reset_index(drop=True)
            label_column = f"risk_label_{horizon}d"
            split = int(len(dataset) * 0.80)
            train = dataset.iloc[:split]
            test = dataset.iloc[split:]
            X_train, y_train = train[FEATURE_COLUMNS], train[label_column]
            X_test, y_test = test[FEATURE_COLUMNS], test[label_column]

            evaluations = {}
            fitted = {}
            for name, model in candidates().items():
                model.fit(X_train, y_train)
                evaluations[name] = metrics(y_test, model.predict(X_test))
                fitted[name] = model

            best_name = max(
                evaluations,
                key=lambda name: (
                    evaluations[name]["balanced_accuracy"]
                    if evaluations[name]["balanced_accuracy"] is not None
                    else -1,
                    evaluations[name]["f1_macro"],
                ),
            )
            model_path = MODEL_DIR / f"risk_model_{currency}_{horizon}d.pkl"
            joblib.dump(fitted[best_name], model_path)
            output["models"][currency][f"{horizon}d"] = {
                "best_model": best_name,
                "model_file": model_path.name,
                "training_rows": int(len(train)),
                "test_rows": int(len(test)),
                "train_start": str(train["date"].min().date()),
                "train_end": str(train["date"].max().date()),
                "test_start": str(test["date"].min().date()),
                "test_end": str(test["date"].max().date()),
                "class_distribution": {
                    str(key): int(value) for key, value in dataset[label_column].value_counts().items()
                },
                "test_class_distribution": {
                    str(key): int(value) for key, value in test[label_column].value_counts().items()
                },
                "evaluation_note": (
                    "Balanced accuracy is unavailable because the chronological test window contains one class."
                    if test[label_column].nunique() < 2
                    else None
                ),
                "evaluations": evaluations,
            }
            print(currency, horizon, best_name, evaluations[best_name])

    (MODEL_DIR / "multicurrency_model_metadata.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
