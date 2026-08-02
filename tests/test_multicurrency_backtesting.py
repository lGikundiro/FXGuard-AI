import unittest

import pandas as pd
from sklearn.dummy import DummyClassifier

from scripts.train_multicurrency_models import (
    FEATURE_COLUMNS,
    assess_reliability,
    purged_chronological_split,
    rolling_origin_backtest,
)
from scripts.train_flexible_horizon_models import (
    apply_training_thresholds,
    build_horizon_dataset,
    chronological_window,
)


def synthetic_dataset(rows=100):
    dates = pd.date_range("2024-01-01", periods=rows, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "risk_label_7d": [
                ("Low", "Medium", "High")[index % 3] for index in range(rows)
            ],
        }
    )
    for index, column in enumerate(FEATURE_COLUMNS):
        frame[column] = [float(row + index) for row in range(rows)]
    return frame


class MultiCurrencyBacktestingTests(unittest.TestCase):
    def test_flexible_dataset_covers_one_to_one_hundred_days(self):
        source = synthetic_dataset(rows=240).drop(columns=["risk_label_7d"])
        source["mid_rate"] = 1000 + source.index.astype(float)

        dataset = build_horizon_dataset(source)

        self.assertEqual(dataset["horizon_days"].min(), 1)
        self.assertEqual(dataset["horizon_days"].max(), 100)
        self.assertTrue((dataset["future_date"] > dataset["date"]).all())

    def test_flexible_split_purges_overlapping_outcomes_and_uses_training_thresholds(self):
        source = synthetic_dataset(rows=240).drop(columns=["risk_label_7d"])
        source["mid_rate"] = 1000 + source.index.astype(float)
        dataset = build_horizon_dataset(source)

        train, test, details = chronological_window(dataset, 0.8, 1.0)
        train, test, thresholds = apply_training_thresholds(train, test)

        self.assertLess(train["future_date"].max(), test["date"].min())
        self.assertGreater(details["purged_training_rows"], 0)
        self.assertEqual(len(thresholds), 100)
        self.assertEqual(set(train["risk_label"]), {"Low", "Medium", "High"})

    def test_final_split_purges_horizon_rows_before_holdout(self):
        dataset = synthetic_dataset()

        train, test = purged_chronological_split(dataset, horizon=7)

        self.assertEqual(len(train), 73)
        self.assertEqual(len(test), 20)
        self.assertEqual(train["date"].max(), dataset.iloc[72]["date"])
        self.assertEqual(test["date"].min(), dataset.iloc[80]["date"])
        self.assertEqual(
            (test["date"].min() - train["date"].max()).days,
            8,
        )

    def test_rolling_origin_backtest_is_forward_only_and_aggregated(self):
        dataset = synthetic_dataset()
        result = rolling_origin_backtest(
            DummyClassifier(strategy="most_frequent"),
            dataset,
            "risk_label_7d",
            horizon=7,
            windows=((0.50, 0.60), (0.60, 0.70), (0.70, 0.80)),
        )

        self.assertEqual(len(result["folds"]), 3)
        for fold in result["folds"]:
            self.assertLess(
                pd.Timestamp(fold["train_end"]),
                pd.Timestamp(fold["test_start"]),
            )
            self.assertEqual(fold["purge_gap_rows"], 7)
            self.assertEqual(fold["test_rows"], 10)
            self.assertEqual(
                sum(fold["test_class_distribution"].values()),
                fold["test_rows"],
            )

        aggregate = result["aggregate_metrics"]
        self.assertIsNotNone(aggregate["accuracy"])
        self.assertIsNotNone(aggregate["balanced_accuracy"])
        self.assertIsNotNone(aggregate["f1_macro"])

    def test_backtest_rejects_a_window_that_uses_final_holdout(self):
        with self.assertRaises(ValueError):
            rolling_origin_backtest(
                DummyClassifier(strategy="most_frequent"),
                synthetic_dataset(),
                "risk_label_7d",
                horizon=7,
                windows=((0.80, 0.90),),
            )

    def test_reliability_gate_rejects_near_chance_model(self):
        model = {"aggregate_metrics": {"balanced_accuracy": 0.40, "f1_macro": 0.35}}
        baseline = {"aggregate_metrics": {"balanced_accuracy": 0.3333, "f1_macro": 0.20}}

        result = assess_reliability(model, baseline)

        self.assertEqual(result["status"], "experimental_not_trustworthy")
        self.assertFalse(result["checks"]["balanced_accuracy_at_least_0_55"])


if __name__ == "__main__":
    unittest.main()
