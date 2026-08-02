"""Train and backtest 7-day and 14-day classifiers for each supported currency."""
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
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.app.modeling import EncodedTargetClassifier


DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "backend" / "models"
REPORT_DIR = ROOT / "reports"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

CURRENCIES = ("USD", "EUR", "KES")
CLASS_ORDER = ("Low", "Medium", "High")
FINAL_TRAIN_RATIO = 0.80
BACKTEST_WINDOWS = ((0.50, 0.60), (0.60, 0.70), (0.70, 0.80))
# These are project deployment gates, not universal scientific cut-offs. They
# are declared before evaluation so a weak result cannot be called trustworthy
# after the fact.
MIN_BALANCED_ACCURACY = 0.55
MIN_MACRO_F1 = 0.45
MIN_BASELINE_IMPROVEMENT = 0.05
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


def class_distribution(labels) -> dict:
    counts = pd.Series(labels).value_counts()
    return {label: int(counts.get(label, 0)) for label in CLASS_ORDER}


def purged_chronological_split(
    dataset: pd.DataFrame,
    horizon: int,
    train_ratio: float = FINAL_TRAIN_RATIO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return an earlier training set and later holdout with a target-leakage gap."""
    test_start = int(len(dataset) * train_ratio)
    if test_start >= len(dataset):
        raise ValueError("Dataset is too small for the requested chronological split.")
    test = dataset.iloc[test_start:].copy()
    target_column = f"future_{horizon}d_date"
    if target_column in dataset.columns:
        test_start_date = test["date"].min()
        eligible = pd.to_datetime(dataset[target_column]) < test_start_date
        train = dataset.iloc[:test_start].loc[eligible.iloc[:test_start]].copy()
    else:
        train_end = test_start - horizon
        if train_end <= 0:
            raise ValueError("Dataset is too small for the requested chronological split.")
        train = dataset.iloc[:train_end].copy()
    if train.empty:
        raise ValueError("Dataset is too small for the requested chronological split.")
    return train, test


def label_with_thresholds(values: pd.Series, low: float, high: float) -> pd.Series:
    labels = pd.Series("High", index=values.index, dtype=object)
    labels.loc[values <= high] = "Medium"
    labels.loc[values <= low] = "Low"
    labels.loc[values.isna()] = None
    return labels


def relabel_from_training(
    train: pd.DataFrame,
    test: pd.DataFrame,
    horizon: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Derive label boundaries from training data only to avoid look-ahead."""
    future_column = f"future_{horizon}d_change"
    label_column = f"risk_label_{horizon}d"
    if future_column not in train.columns:
        return train, test, {}
    low = float(train[future_column].quantile(0.50))
    high = float(train[future_column].quantile(0.80))
    train = train.copy()
    test = test.copy()
    train[label_column] = label_with_thresholds(train[future_column], low, high)
    test[label_column] = label_with_thresholds(test[future_column], low, high)
    return train, test, {"low_max": low, "medium_max": high, "source": "training_window_only"}


def rolling_origin_backtest(
    base_model,
    dataset: pd.DataFrame,
    label_column: str,
    horizon: int,
    windows=BACKTEST_WINDOWS,
) -> dict:
    """Evaluate one candidate on expanding, forward-only windows before holdout."""
    folds = []
    previous_test_end = 0

    for fold_number, (train_ratio, test_ratio) in enumerate(windows, start=1):
        test_start = int(len(dataset) * train_ratio)
        test_end = int(len(dataset) * test_ratio)
        if not 0 < train_ratio < test_ratio <= FINAL_TRAIN_RATIO:
            raise ValueError("Backtest windows must be ordered and end within the training period.")
        if test_end <= test_start:
            raise ValueError("Dataset is too small for the requested backtest windows.")
        if test_start < previous_test_end:
            raise ValueError("Backtest test windows must not overlap.")

        train, _ = purged_chronological_split(
            dataset.iloc[:test_end].copy(),
            horizon,
            train_ratio=test_start / test_end,
        )
        test = dataset.iloc[test_start:test_end].copy()
        train, test, fold_thresholds = relabel_from_training(train, test, horizon)
        model = clone(base_model)
        model.fit(train[FEATURE_COLUMNS], train[label_column])
        fold_metrics = metrics(test[label_column], model.predict(test[FEATURE_COLUMNS]))
        folds.append(
            {
                "fold": fold_number,
                "training_rows": int(len(train)),
                "test_rows": int(len(test)),
                "purge_gap_rows": int(horizon),
                "actual_purged_rows": int(test_start - len(train)),
                "train_start": str(train["date"].min().date()),
                "train_end": str(train["date"].max().date()),
                "test_start": str(test["date"].min().date()),
                "test_end": str(test["date"].max().date()),
                "train_class_distribution": class_distribution(train[label_column]),
                "test_class_distribution": class_distribution(test[label_column]),
                "metrics": fold_metrics,
                "label_thresholds": fold_thresholds,
            }
        )
        previous_test_end = test_end

    aggregate_metrics = {}
    for metric_name in ("accuracy", "balanced_accuracy", "f1_macro"):
        values = [
            fold["metrics"][metric_name]
            for fold in folds
            if fold["metrics"][metric_name] is not None
        ]
        aggregate_metrics[metric_name] = (
            round(float(sum(values) / len(values)), 4) if values else None
        )

    return {
        "aggregate_metrics": aggregate_metrics,
        "folds": folds,
    }


def backtest_selection_score(backtest: dict) -> tuple:
    aggregate = backtest["aggregate_metrics"]
    return (
        aggregate["balanced_accuracy"]
        if aggregate["balanced_accuracy"] is not None
        else -1.0,
        aggregate["f1_macro"] if aggregate["f1_macro"] is not None else -1.0,
        aggregate["accuracy"] if aggregate["accuracy"] is not None else -1.0,
    )


def assess_reliability(selected: dict, baseline: dict) -> dict:
    model_metrics = selected["aggregate_metrics"]
    baseline_metrics = baseline["aggregate_metrics"]
    balanced = model_metrics["balanced_accuracy"]
    macro_f1 = model_metrics["f1_macro"]
    baseline_balanced = baseline_metrics["balanced_accuracy"]
    improvement = None if balanced is None or baseline_balanced is None else balanced - baseline_balanced
    checks = {
        "balanced_accuracy_at_least_0_55": balanced is not None and balanced >= MIN_BALANCED_ACCURACY,
        "macro_f1_at_least_0_45": macro_f1 is not None and macro_f1 >= MIN_MACRO_F1,
        "balanced_accuracy_beats_baseline_by_0_05": improvement is not None and improvement >= MIN_BASELINE_IMPROVEMENT,
    }
    return {
        "status": "meets_provisional_gate" if all(checks.values()) else "experimental_not_trustworthy",
        "gate_is_project_defined": True,
        "checks": checks,
        "balanced_accuracy_improvement_over_baseline": (
            None if improvement is None else round(float(improvement), 4)
        ),
        "required": {
            "mean_balanced_accuracy": MIN_BALANCED_ACCURACY,
            "mean_macro_f1": MIN_MACRO_F1,
            "minimum_balanced_accuracy_improvement_over_baseline": MIN_BASELINE_IMPROVEMENT,
        },
    }


def format_metric(value) -> str:
    return "unavailable" if value is None else f"{value:.4f}"


def write_evaluation_report(output: dict) -> Path:
    lines = [
        "# FXGuard AI Multicurrency Model Evaluation",
        "",
        f"Generated: {output['generated_at']}",
        "",
        (
            "Each candidate is evaluated with three expanding-window rolling-origin "
            "folds inside the first 80% of the history. The selected model is then "
            "evaluated once on the untouched final 20% holdout."
        ),
        "",
        (
            "Any training row whose future outcome date reaches a test window is "
            "removed so labels derived from future rates cannot cross the boundary."
        ),
        (
            "After model selection and holdout evaluation, the selected production "
            "model is refitted on all labeled observations."
        ),
        "",
    ]

    for currency in CURRENCIES:
        lines.extend([f"## {currency}/RWF", ""])
        for horizon in (7, 14):
            info = output["models"][currency][f"{horizon}d"]
            selected_backtest = info["backtest"]["candidates"][info["best_model"]]
            holdout = info["evaluations"][info["best_model"]]
            aggregate = selected_backtest["aggregate_metrics"]
            lines.extend(
                [
                    f"### {horizon}-day horizon",
                    "",
                    f"- Selected model: `{info['best_model']}`",
                    (
                        f"- Final training window: {info['train_start']} to "
                        f"{info['train_end']} ({info['training_rows']} rows)"
                    ),
                    (
                        f"- Untouched holdout: {info['test_start']} to "
                        f"{info['test_end']} ({info['test_rows']} rows)"
                    ),
                    (
                        f"- Production refit: {info['deployment_train_start']} to "
                        f"{info['deployment_train_end']} "
                        f"({info['deployment_training_rows']} rows)"
                    ),
                    (
                        f"- Outcome-date purge: {info['actual_purged_rows']} official "
                        "observations removed at the final holdout boundary"
                    ),
                    f"- Reliability status: `{info['reliability']['status']}`",
                    (
                        "- Most-frequent baseline: balanced accuracy "
                        f"{format_metric(info['baseline']['aggregate_metrics']['balanced_accuracy'])}, "
                        "macro F1 "
                        f"{format_metric(info['baseline']['aggregate_metrics']['f1_macro'])}"
                    ),
                    (
                        "- Mean backtest metrics: accuracy "
                        f"{format_metric(aggregate['accuracy'])}, balanced accuracy "
                        f"{format_metric(aggregate['balanced_accuracy'])}, macro F1 "
                        f"{format_metric(aggregate['f1_macro'])}"
                    ),
                    (
                        "- Final holdout metrics: accuracy "
                        f"{format_metric(holdout['accuracy'])}, balanced accuracy "
                        f"{format_metric(holdout['balanced_accuracy'])}, macro F1 "
                        f"{format_metric(holdout['f1_macro'])}"
                    ),
                    "",
                    "Rolling-origin folds:",
                    "",
                ]
            )
            for fold in selected_backtest["folds"]:
                fold_metrics = fold["metrics"]
                lines.append(
                    (
                        f"- Fold {fold['fold']}: train through {fold['train_end']}; "
                        f"test {fold['test_start']} to {fold['test_end']}; "
                        f"purged {fold['actual_purged_rows']} boundary observations; "
                        f"balanced accuracy "
                        f"{format_metric(fold_metrics['balanced_accuracy'])}; "
                        f"macro F1 {format_metric(fold_metrics['f1_macro'])}"
                    )
                )
            lines.append("")

    report_path = REPORT_DIR / "multicurrency_model_evaluation.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


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
            train, test = purged_chronological_split(dataset, horizon)
            train, test, holdout_thresholds = relabel_from_training(train, test, horizon)
            X_train, y_train = train[FEATURE_COLUMNS], train[label_column]
            X_test, y_test = test[FEATURE_COLUMNS], test[label_column]

            evaluations = {}
            backtests = {}
            candidate_models = candidates()
            baseline_backtest = rolling_origin_backtest(
                DummyClassifier(strategy="most_frequent"),
                dataset,
                label_column,
                horizon,
            )
            for name, model in candidate_models.items():
                backtests[name] = rolling_origin_backtest(
                    model,
                    dataset,
                    label_column,
                    horizon,
                )
                model.fit(X_train, y_train)
                evaluations[name] = metrics(y_test, model.predict(X_test))

            best_name = max(backtests, key=lambda name: backtest_selection_score(backtests[name]))
            reliability = assess_reliability(backtests[best_name], baseline_backtest)
            deployment_model = clone(candidate_models[best_name])
            deployment_model.fit(dataset[FEATURE_COLUMNS], dataset[label_column])
            model_path = MODEL_DIR / f"risk_model_{currency}_{horizon}d.pkl"
            joblib.dump(deployment_model, model_path)
            output["models"][currency][f"{horizon}d"] = {
                "best_model": best_name,
                "selection_method": (
                    "Highest mean rolling-origin balanced accuracy, then macro F1 "
                    "and accuracy; final holdout excluded from model selection."
                ),
                "reliability": reliability,
                "baseline": baseline_backtest,
                "holdout_label_thresholds": holdout_thresholds,
                "model_file": model_path.name,
                "training_rows": int(len(train)),
                "test_rows": int(len(test)),
                "deployment_training_rows": int(len(dataset)),
                "purge_gap_rows": int(horizon),
                "purge_rule": "remove training rows whose future outcome date reaches the test period",
                "actual_purged_rows": int(int(len(dataset) * FINAL_TRAIN_RATIO) - len(train)),
                "train_start": str(train["date"].min().date()),
                "train_end": str(train["date"].max().date()),
                "test_start": str(test["date"].min().date()),
                "test_end": str(test["date"].max().date()),
                "deployment_train_start": str(dataset["date"].min().date()),
                "deployment_train_end": str(dataset["date"].max().date()),
                "class_distribution": class_distribution(dataset[label_column]),
                "test_class_distribution": class_distribution(test[label_column]),
                "evaluation_note": (
                    "Balanced accuracy is unavailable because the chronological test window contains one class."
                    if test[label_column].nunique() < 2
                    else None
                ),
                "evaluations": evaluations,
                "backtest": {
                    "strategy": "expanding-window rolling-origin",
                    "scope": "first 80% of observations; final 20% reserved as holdout",
                    "fold_count": len(BACKTEST_WINDOWS),
                    "purge_gap_rows": int(horizon),
                    "candidates": backtests,
                },
            }
            print(
                currency,
                horizon,
                best_name,
                "backtest",
                backtests[best_name]["aggregate_metrics"],
                "holdout",
                evaluations[best_name],
                reliability["status"],
            )

    (MODEL_DIR / "multicurrency_model_metadata.json").write_text(
        json.dumps(output, indent=2), encoding="utf-8"
    )
    report_path = write_evaluation_report(output)
    print("Wrote", report_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
