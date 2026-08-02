"""Train one 1-to-100-day horizon-aware risk classifier per currency."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.dummy import DummyClassifier

from scripts.train_multicurrency_models import (
    BACKTEST_WINDOWS,
    CURRENCIES,
    FEATURE_COLUMNS,
    FINAL_TRAIN_RATIO,
    assess_reliability,
    backtest_selection_score,
    candidates,
    class_distribution,
    format_metric,
    metrics,
)

DATA_PATH = ROOT / "data" / "processed" / "multicurrency_features_and_labels.csv"
MODEL_DIR = ROOT / "backend" / "models"
REPORT_PATH = ROOT / "reports" / "flexible_horizon_model_evaluation.md"
METADATA_PATH = MODEL_DIR / "flexible_horizon_model_metadata.json"

MIN_HORIZON_DAYS = 1
MAX_HORIZON_DAYS = 100
MODEL_FEATURE_COLUMNS = [*FEATURE_COLUMNS, "horizon_days"]
HORIZON_BANDS = ((1, 14), (15, 30), (31, 60), (61, 100))


def build_horizon_dataset(currency_features: pd.DataFrame) -> pd.DataFrame:
    """Create one supervised row per observation date and requested horizon."""
    source = currency_features.sort_values("date").copy()
    ready = source.dropna(subset=FEATURE_COLUMNS).copy()
    lookup = source[["date", "mid_rate"]].rename(
        columns={"date": "future_date", "mid_rate": "future_rate"}
    )
    frames = []
    for horizon in range(MIN_HORIZON_DAYS, MAX_HORIZON_DAYS + 1):
        targets = ready[["date", *FEATURE_COLUMNS]].copy()
        targets["horizon_days"] = horizon
        targets["target_date"] = targets["date"] + pd.Timedelta(days=horizon)
        matched = pd.merge_asof(
            targets.sort_values("target_date"),
            lookup.sort_values("future_date"),
            left_on="target_date",
            right_on="future_date",
            direction="forward",
        )
        matched["future_change"] = matched["future_rate"] / matched["mid_rate"] - 1
        frames.append(matched.drop(columns=["target_date", "future_rate"]))
    return (
        pd.concat(frames, ignore_index=True)
        .dropna(subset=["future_date", "future_change"])
        .sort_values(["date", "horizon_days"])
        .reset_index(drop=True)
    )


def threshold_table(training: pd.DataFrame) -> pd.DataFrame:
    grouped = training.groupby("horizon_days")["future_change"]
    table = grouped.quantile([0.50, 0.80]).unstack()
    table.columns = ["low_max", "medium_max"]
    return table


def apply_training_thresholds(
    training: pd.DataFrame,
    evaluation: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Label both sets using boundaries learned only from the training dates."""
    thresholds = threshold_table(training)

    def apply(frame: pd.DataFrame) -> pd.DataFrame:
        labelled = frame.join(thresholds, on="horizon_days").copy()
        if labelled[["low_max", "medium_max"]].isna().any().any():
            raise ValueError("A requested horizon has no training threshold.")
        labelled["risk_label"] = np.select(
            [
                labelled["future_change"] <= labelled["low_max"],
                labelled["future_change"] <= labelled["medium_max"],
            ],
            ["Low", "Medium"],
            default="High",
        )
        return labelled

    return apply(training), apply(evaluation), thresholds


def chronological_window(
    dataset: pd.DataFrame,
    train_ratio: float,
    test_ratio: float,
    final_holdout_start: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    dates = pd.Index(sorted(dataset["date"].unique()))
    test_start_index = int(len(dates) * train_ratio)
    test_end_index = int(len(dates) * test_ratio)
    if test_start_index <= 0 or test_end_index <= test_start_index:
        raise ValueError("Dataset is too small for the requested chronological window.")
    test_start = pd.Timestamp(dates[test_start_index])
    test_end = pd.Timestamp(dates[test_end_index]) if test_end_index < len(dates) else None

    training = dataset.loc[
        (dataset["date"] < test_start) & (dataset["future_date"] < test_start)
    ].copy()
    test_mask = dataset["date"].ge(test_start)
    if test_end is not None:
        test_mask &= dataset["date"].lt(test_end)
    if final_holdout_start is not None:
        test_mask &= dataset["future_date"].lt(final_holdout_start)
    evaluation = dataset.loc[test_mask].copy()
    if training.empty or evaluation.empty:
        raise ValueError("Chronological window contains no usable rows.")
    return training, evaluation, {
        "train_start": str(training["date"].min().date()),
        "train_end": str(training["date"].max().date()),
        "test_start": str(evaluation["date"].min().date()),
        "test_end": str(evaluation["date"].max().date()),
        "training_rows": int(len(training)),
        "test_rows": int(len(evaluation)),
        "purged_training_rows": int(dataset.loc[dataset["date"] < test_start].shape[0] - len(training)),
    }


def band_metrics(frame: pd.DataFrame, predictions) -> dict:
    scored = frame[["horizon_days", "risk_label"]].copy()
    scored["prediction"] = predictions
    output = {}
    for start, end in HORIZON_BANDS:
        selected = scored.loc[scored["horizon_days"].between(start, end)]
        output[f"{start}-{end}d"] = {
            "rows": int(len(selected)),
            **metrics(selected["risk_label"], selected["prediction"]),
        }
    return output


def rolling_backtest(base_model, dataset: pd.DataFrame) -> dict:
    unique_dates = pd.Index(sorted(dataset["date"].unique()))
    final_start = pd.Timestamp(unique_dates[int(len(unique_dates) * FINAL_TRAIN_RATIO)])
    folds = []
    for fold, (train_ratio, test_ratio) in enumerate(BACKTEST_WINDOWS, start=1):
        train, test, details = chronological_window(
            dataset,
            train_ratio,
            test_ratio,
            final_holdout_start=final_start,
        )
        train, test, thresholds = apply_training_thresholds(train, test)
        model = clone(base_model)
        model.fit(train[MODEL_FEATURE_COLUMNS], train["risk_label"])
        predictions = model.predict(test[MODEL_FEATURE_COLUMNS])
        folds.append(
            {
                "fold": fold,
                **details,
                "metrics": metrics(test["risk_label"], predictions),
                "horizon_band_metrics": band_metrics(test, predictions),
                "train_class_distribution": class_distribution(train["risk_label"]),
                "test_class_distribution": class_distribution(test["risk_label"]),
                "threshold_horizons": int(len(thresholds)),
            }
        )
    aggregate = {
        name: round(float(np.mean([fold["metrics"][name] for fold in folds])), 4)
        for name in ("accuracy", "balanced_accuracy", "f1_macro")
    }
    return {"aggregate_metrics": aggregate, "folds": folds}


def serialise_thresholds(thresholds: pd.DataFrame) -> dict:
    return {
        str(int(horizon)): {
            "low_max": float(row["low_max"]),
            "medium_max": float(row["medium_max"]),
        }
        for horizon, row in thresholds.iterrows()
    }


def write_report(output: dict) -> None:
    lines = [
        "# FXGuard AI Flexible-Horizon Model Evaluation",
        "",
        f"Generated: {output['generated_at']}",
        "",
        (
            "Each currency has one horizon-aware classifier. The requested number of calendar "
            "days (1–100) is a model feature, and training contains outcomes for every integer horizon."
        ),
        "",
        (
            "Evaluation splits on observation dates. A training row is removed whenever its future "
            "outcome date reaches the test period, with up to a 100-day boundary purge. Risk-label "
            "thresholds are learned independently for each horizon from training dates only."
        ),
        "",
    ]
    for currency in CURRENCIES:
        info = output["models"][currency]
        selected = info["backtest"]["candidates"][info["best_model"]]
        holdout = info["holdout"]
        lines.extend(
            [
                f"## {currency}/RWF",
                "",
                f"- Selected model: `{info['best_model']}`",
                f"- Reliability status: `{info['reliability']['status']}`",
                f"- Supervised rows: {info['dataset_rows']}",
                (
                    "- Mean rolling metrics: accuracy "
                    f"{format_metric(selected['aggregate_metrics']['accuracy'])}, balanced accuracy "
                    f"{format_metric(selected['aggregate_metrics']['balanced_accuracy'])}, macro F1 "
                    f"{format_metric(selected['aggregate_metrics']['f1_macro'])}"
                ),
                (
                    "- Holdout metrics: accuracy "
                    f"{format_metric(holdout['metrics']['accuracy'])}, balanced accuracy "
                    f"{format_metric(holdout['metrics']['balanced_accuracy'])}, macro F1 "
                    f"{format_metric(holdout['metrics']['f1_macro'])}"
                ),
                "",
                "Holdout metrics by requested payment period:",
                "",
            ]
        )
        for band, values in holdout["horizon_band_metrics"].items():
            lines.append(
                f"- {band}: balanced accuracy {format_metric(values['balanced_accuracy'])}; "
                f"macro F1 {format_metric(values['f1_macro'])}; {values['rows']} rows"
            )
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    features = pd.read_csv(DATA_PATH, parse_dates=["date"])
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_type": "horizon-aware multiclass classification",
        "supported_horizon_days": {"minimum": MIN_HORIZON_DAYS, "maximum": MAX_HORIZON_DAYS},
        "feature_columns": MODEL_FEATURE_COLUMNS,
        "models": {},
    }
    for currency in CURRENCIES:
        dataset = build_horizon_dataset(features.loc[features["currency"] == currency])
        unique_dates = pd.Index(sorted(dataset["date"].unique()))
        final_start = pd.Timestamp(unique_dates[int(len(unique_dates) * FINAL_TRAIN_RATIO)])
        train, holdout, holdout_window = chronological_window(
            dataset, FINAL_TRAIN_RATIO, 1.0
        )
        train, holdout, holdout_thresholds = apply_training_thresholds(train, holdout)

        candidate_backtests = {}
        holdout_evaluations = {}
        available_candidates = candidates()
        for name, estimator in available_candidates.items():
            candidate_backtests[name] = rolling_backtest(estimator, dataset)
            fitted = clone(estimator).fit(train[MODEL_FEATURE_COLUMNS], train["risk_label"])
            predictions = fitted.predict(holdout[MODEL_FEATURE_COLUMNS])
            holdout_evaluations[name] = {
                "metrics": metrics(holdout["risk_label"], predictions),
                "horizon_band_metrics": band_metrics(holdout, predictions),
            }

        baseline = rolling_backtest(DummyClassifier(strategy="most_frequent"), dataset)
        best_name = max(
            candidate_backtests,
            key=lambda name: backtest_selection_score(candidate_backtests[name]),
        )
        reliability = assess_reliability(candidate_backtests[best_name], baseline)

        deployment = dataset.copy()
        deployment_thresholds = threshold_table(deployment)
        deployment = deployment.join(deployment_thresholds, on="horizon_days")
        deployment["risk_label"] = np.select(
            [
                deployment["future_change"] <= deployment["low_max"],
                deployment["future_change"] <= deployment["medium_max"],
            ],
            ["Low", "Medium"],
            default="High",
        )
        production_model = clone(available_candidates[best_name]).fit(
            deployment[MODEL_FEATURE_COLUMNS], deployment["risk_label"]
        )
        model_path = MODEL_DIR / f"risk_model_{currency}_flexible.pkl"
        joblib.dump(production_model, model_path)

        output["models"][currency] = {
            "best_model": best_name,
            "model_file": model_path.name,
            "dataset_rows": int(len(dataset)),
            "observation_dates": int(dataset["date"].nunique()),
            "dataset_start": str(dataset["date"].min().date()),
            "dataset_end": str(dataset["date"].max().date()),
            "final_holdout_start": str(final_start.date()),
            "selection_method": "mean rolling balanced accuracy, then macro F1 and accuracy",
            "reliability": reliability,
            "baseline": baseline,
            "backtest": {"candidates": candidate_backtests},
            "holdout": {**holdout_evaluations[best_name], **holdout_window},
            "holdout_label_thresholds": serialise_thresholds(holdout_thresholds),
            "deployment_label_thresholds": serialise_thresholds(deployment_thresholds),
        }
        print(
            currency,
            best_name,
            candidate_backtests[best_name]["aggregate_metrics"],
            holdout_evaluations[best_name]["metrics"],
            reliability["status"],
        )

    METADATA_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")
    write_report(output)
    print("Wrote", REPORT_PATH.relative_to(ROOT))


if __name__ == "__main__":
    main()
