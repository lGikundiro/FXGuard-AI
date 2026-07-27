import unittest

import pandas as pd
from sklearn.dummy import DummyClassifier

from scripts.train_multicurrency_models import (
    FEATURE_COLUMNS,
    purged_chronological_split,
    rolling_origin_backtest,
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


if __name__ == "__main__":
    unittest.main()
