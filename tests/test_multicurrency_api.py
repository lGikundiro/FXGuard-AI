import tempfile
import unittest
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from fastapi import HTTPException
from openpyxl import load_workbook

from backend.app.main import (
    FEEDBACK_COLUMNS,
    GOOGLE_FORM_ENTRY_IDS,
    FeedbackRequest,
    RiskRequest,
    append_feedback_to_google_sheet,
    build_excel_report,
    currencies,
    feedback,
    history,
    latest_rate,
    predict_risk,
    rwanda_today,
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
                    RiskRequest(
                        currency=currency,
                        amount=1000,
                        payment_date=rwanda_today() + timedelta(days=37),
                    )
                )
                self.assertEqual(payload["currency"], currency)
                self.assertEqual(payload["amount"], 1000)
                self.assertEqual(payload["horizon_days"], 37)
                self.assertEqual(payload["payment_date"], str(rwanda_today() + timedelta(days=37)))
                self.assertIn(payload["risk_level"], {"Low", "Medium", "High"})
                self.assertGreater(payload["current_cost_rwf"], 0)
                self.assertGreaterEqual(payload["confidence_score"], 0)
                self.assertLessEqual(payload["confidence_score"], 1)
                self.assertTrue(payload["score_is_approximate"])
                self.assertEqual(payload["score_calibration"], "uncalibrated")
                self.assertAlmostEqual(
                    sum(payload["class_probabilities"].values()), 1,
                    places=3,
                )

    def test_unknown_currency_is_rejected(self):
        for currency in ("UGX", "GBP"):
            with self.subTest(currency=currency):
                with self.assertRaises(HTTPException) as context:
                    latest_rate(currency)
                self.assertEqual(context.exception.status_code, 400)

    def test_payment_date_must_be_between_one_and_one_hundred_days(self):
        for days in (0, 101):
            with self.subTest(days=days):
                with self.assertRaises(HTTPException) as context:
                    predict_risk(
                        RiskRequest(
                            currency="USD",
                            amount=1000,
                            payment_date=rwanda_today() + timedelta(days=days),
                        )
                    )
                self.assertEqual(context.exception.status_code, 400)

    def test_payment_date_boundary_days_are_supported(self):
        for days in (1, 100):
            with self.subTest(days=days):
                payload = predict_risk(
                    RiskRequest(
                        currency="USD",
                        amount=1000,
                        payment_date=rwanda_today() + timedelta(days=days),
                    )
                )
                self.assertEqual(payload["horizon_days"], days)

    def test_excel_export_is_a_valid_workbook(self):
        result = predict_risk(
            RiskRequest(
                currency="KES",
                amount=3000,
                payment_date=rwanda_today() + timedelta(days=45),
            )
        )
        workbook = load_workbook(build_excel_report(result), data_only=True)
        sheet = workbook["Risk Assessment"]
        self.assertEqual(sheet["A1"].value, "FXGUARD AI — PAYMENT CHECK REPORT")
        self.assertIn("SUMMARY", [cell.value for cell in sheet["A"]])
        self.assertIn(
            "HOW FXGUARD COMPARED THE RISK LEVELS",
            [cell.value for cell in sheet["A"]],
        )
        self.assertIn("WHAT THIS RESULT IS BASED ON", [cell.value for cell in sheet["A"]])

    @patch("backend.app.main.GOOGLE_SHEETS_WEBHOOK_URL", "")
    @patch("backend.app.main.urllib.request.urlopen")
    def test_feedback_maps_to_existing_google_form_columns(self, mock_urlopen):
        response = MagicMock()
        response.getcode.return_value = 200
        mock_urlopen.return_value.__enter__.return_value = response
        feedback = {
            "participant_name": "Test participant",
            "import_category": "Medicine",
            "phone_number": "+250700000000",
            "clarity_rating": 4,
            "usefulness_rating": 5,
            "comment": "Clear and useful",
        }

        result = append_feedback_to_google_sheet(feedback)

        self.assertEqual(result["status"], "saved")
        request = mock_urlopen.call_args.args[0]
        submitted = urllib.parse.parse_qs(request.data.decode("utf-8"))
        for field, entry_id in GOOGLE_FORM_ENTRY_IDS.items():
            self.assertEqual(submitted[entry_id], [str(feedback[field])])

    def test_feedback_appends_to_local_excel_backup(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            feedback_file = Path(temporary_directory) / "prototype_feedback.xlsx"
            request = FeedbackRequest(
                participant_name="Test participant",
                import_category="Raw materials",
                phone_number="+250700000000",
                clarity_rating=4,
                usefulness_rating=5,
                comment="Clear and useful",
            )
            with (
                patch("backend.app.main.FEEDBACK_FILE", feedback_file),
                patch(
                    "backend.app.main.append_feedback_to_google_sheet",
                    return_value={"enabled": True, "status": "saved"},
                ),
            ):
                first_result = feedback(request)
                second_result = feedback(request)

            saved = pd.read_excel(feedback_file, dtype={"phone_number": str})
            self.assertEqual(first_result["status"], "saved")
            self.assertEqual(second_result["status"], "saved")
            self.assertEqual(saved.columns.tolist(), FEEDBACK_COLUMNS)
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved.loc[0, "phone_number"], "+250700000000")


if __name__ == "__main__":
    unittest.main()
