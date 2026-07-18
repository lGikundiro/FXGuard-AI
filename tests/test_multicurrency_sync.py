import unittest

import pandas as pd

from scripts.sync_multicurrency_rates import (
    RAW_FILES,
    build_daily_calendar,
    load_raw_workbook,
)


class MultiCurrencySyncTests(unittest.TestCase):
    def test_uploaded_workbooks_are_valid_bnr_histories(self):
        for currency in ("USD", "EUR", "KES"):
            with self.subTest(currency=currency):
                frame = load_raw_workbook(currency, RAW_FILES[currency])
                self.assertGreaterEqual(len(frame), 1000)
                self.assertEqual(set(frame["currency"]), {currency})
                self.assertTrue(frame["date"].is_monotonic_increasing)
                self.assertFalse(frame["date"].duplicated().any())
                self.assertTrue(frame["source"].eq("National Bank of Rwanda Excel export").all())
                self.assertTrue(frame["mid_rate"].equals(frame["average_rate"]))
                self.assertTrue((frame["buying_rate"] <= frame["average_rate"]).all())
                self.assertTrue((frame["average_rate"] <= frame["selling_rate"]).all())

    def test_daily_calendar_does_not_backfill_before_currency_history(self):
        observations = pd.DataFrame(
            [
                self._observation("2024-01-01", "USD", 1000),
                self._observation("2024-01-03", "USD", 1002),
                self._observation("2024-02-01", "KES", 10),
                self._observation("2024-02-03", "KES", 12),
            ]
        )

        daily = build_daily_calendar(observations)
        coverage = daily.groupby("currency")["date"].agg(["min", "max"])

        self.assertEqual(coverage.loc["USD", "min"], pd.Timestamp("2024-01-01"))
        self.assertEqual(coverage.loc["USD", "max"], pd.Timestamp("2024-01-03"))
        self.assertEqual(coverage.loc["KES", "min"], pd.Timestamp("2024-02-01"))
        self.assertEqual(coverage.loc["KES", "max"], pd.Timestamp("2024-02-03"))

    @staticmethod
    def _observation(observed_date, currency, rate):
        return {
            "date": pd.Timestamp(observed_date),
            "currency": currency,
            "buying_rate": rate - 1,
            "average_rate": rate,
            "selling_rate": rate + 1,
            "mid_rate": rate,
            "is_official_observation": 1,
            "source": "test",
            "rate_type": "test",
        }


if __name__ == "__main__":
    unittest.main()
