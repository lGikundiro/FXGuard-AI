import unittest

from fastapi import HTTPException
from openpyxl import load_workbook

from backend.app.main import (
    RiskRequest,
    build_excel_report,
    currencies,
    history,
    latest_rate,
    predict_risk,
)


class MultiCurrencyApiTests(unittest.TestCase):
    def test_supported_currencies(self):
        catalog = currencies()["currencies"]
        self.assertEqual(
            [item["code"] for item in catalog],
            ["USD", "EUR", "KES"],
        )
        self.assertEqual(
            {item["code"]: item["symbol"] for item in catalog},
            {"USD": "$", "EUR": "\u20ac", "KES": "KSh"},
        )

    def test_rate_history_and_prediction_for_each_currency(self):
        for currency in ("USD", "EUR", "KES"):
            with self.subTest(currency=currency):
                latest = latest_rate(currency)
                self.assertEqual(latest["pair"], f"{currency}/RWF")
                self.assertGreater(latest["mid_rate"], 0)
                self.assertLessEqual(latest["buying_rate"], latest["mid_rate"])
                self.assertLessEqual(latest["mid_rate"], latest["selling_rate"])
                self.assertEqual(latest["source"], "National Bank of Rwanda Excel export")

                rate_history = history(days=30, currency=currency)
                self.assertEqual(len(rate_history["points"]), 30)

                payload = predict_risk(
                    RiskRequest(currency=currency, amount=1000, horizon=7)
                )
                self.assertEqual(payload["currency"], currency)
                self.assertEqual(payload["amount"], 1000)
                self.assertIn(payload["risk_level"], {"Low", "Medium", "High"})
                self.assertGreater(payload["current_cost_rwf"], 0)

    def test_unknown_currency_is_rejected(self):
        for currency in ("UGX", "GBP"):
            with self.subTest(currency=currency):
                with self.assertRaises(HTTPException) as context:
                    latest_rate(currency)
                self.assertEqual(context.exception.status_code, 400)

    def test_excel_export_is_a_valid_workbook(self):
        result = predict_risk(RiskRequest(currency="KES", amount=3000, horizon=7))
        workbook = load_workbook(build_excel_report(result), data_only=True)
        sheet = workbook["Risk Assessment"]
        self.assertEqual(sheet["A1"].value, "FXGUARD AI — RISK ASSESSMENT REPORT")
        self.assertIn("SUMMARY", [cell.value for cell in sheet["A"]])
        self.assertIn(
            "HOW STRONGLY EACH RISK LEVEL IS SUPPORTED",
            [cell.value for cell in sheet["A"]],
        )
        self.assertIn("WHAT THIS RESULT IS BASED ON", [cell.value for cell in sheet["A"]])


if __name__ == "__main__":
    unittest.main()
