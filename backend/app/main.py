from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel, Field

from backend.app.rates import (
    CURRENCY_INFO,
    SUPPORTED_CURRENCIES,
    combined_daily,
    latest_feature_row as latest_currency_feature_row,
    provider_status,
    validate_currency,
)

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "backend" / "models"
FRONTEND_DIR = ROOT / "frontend"
FEEDBACK_DIR = ROOT / "reports" / "feedback"
FEEDBACK_FILE = FEEDBACK_DIR / "prototype_feedback.xlsx"
FEEDBACK_FORM_NAME = os.getenv("FEEDBACK_FORM_NAME", "FXGuard AI User feedback")
GOOGLE_SHEETS_WEBHOOK_URL = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "").strip()

FEATURE_COLUMNS = [
    "mid_rate", "daily_return", "return_7d", "return_14d", "ma_7", "ma_14", "ma_30",
    "ma_gap", "volatility_7d", "volatility_14d", "volatility_30d", "momentum_7d",
    "momentum_14d", "spread", "spread_pct", "depreciation_days_7d", "depreciation_days_14d",
]

app = FastAPI(
    title="FXGuard AI API",
    description="Multi-currency exchange-rate risk forecasting and decision support for Rwanda-based importers.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


class RiskRequest(BaseModel):
    currency: str = Field(default="USD", description="Invoice currency: USD, EUR, or KES.")
    amount: float = Field(default=10000, gt=0, description="Supplier invoice amount in the selected currency.")
    horizon: int = Field(default=7, description="Prediction horizon in days: 7 or 14.")


class FeedbackRequest(BaseModel):
    participant_name: Optional[str] = None
    import_category: Optional[str] = None
    phone_number: Optional[str] = None
    clarity_rating: int = Field(ge=1, le=5)
    usefulness_rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


FEEDBACK_COLUMNS = [
    "submitted_at",
    "participant_name",
    "import_category",
    "phone_number",
    "clarity_rating",
    "usefulness_rating",
    "comment",
]


_cache = {}


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def project_path_label(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def append_feedback_to_google_sheet(feedback_data: dict) -> dict:
    if not GOOGLE_SHEETS_WEBHOOK_URL:
        return {"enabled": False, "status": "not_configured"}

    payload = {
        "form_name": FEEDBACK_FORM_NAME,
        "columns": FEEDBACK_COLUMNS,
        "response": {column: feedback_data.get(column) for column in FEEDBACK_COLUMNS},
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        GOOGLE_SHEETS_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            response_text = response.read().decode("utf-8").strip()
            response_body = json.loads(response_text) if response_text else {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"enabled": True, "status": "failed", "detail": str(exc)}

    if isinstance(response_body, dict) and response_body.get("status") in {"saved", "ok"}:
        return {"enabled": True, "status": "saved"}
    return {"enabled": True, "status": "unknown_response"}


def load_model(currency: str, horizon: int):
    try:
        currency = validate_currency(currency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if horizon not in (7, 14):
        raise HTTPException(status_code=400, detail="Horizon must be 7 or 14 days.")
    key = f"model_{currency}_{horizon}d"
    if key not in _cache:
        path = MODEL_DIR / f"risk_model_{currency}_{horizon}d.pkl"
        if not path.exists():
            raise HTTPException(status_code=500, detail=f"Model not found: {path}")
        _cache[key] = joblib.load(path)
    return _cache[key]


def load_features():
    if "features" not in _cache:
        path = DATA_DIR / "exchange_rates_features_and_labels_4year.csv"
        if not path.exists():
            raise HTTPException(status_code=500, detail="Feature dataset is missing.")
        df = pd.read_csv(path, parse_dates=["date"])
        df = df.sort_values("date").reset_index(drop=True)
        _cache["features"] = df
    return _cache["features"]


def load_daily_calendar():
    if "daily" not in _cache:
        path = DATA_DIR / "exchange_rates_daily_calendar_4year.csv"
        if not path.exists():
            raise HTTPException(status_code=500, detail="Daily calendar dataset is missing.")
        df = pd.read_csv(path, parse_dates=["date"])
        df = df.sort_values("date").reset_index(drop=True)
        _cache["daily"] = df
    return _cache["daily"]


def latest_feature_row():
    df = load_features()
    required = df.dropna(subset=FEATURE_COLUMNS)
    if required.empty:
        raise HTTPException(status_code=500, detail="No feature row available for prediction.")
    return required.iloc[-1]


def risk_guidance(risk: str, currency: str = "USD") -> List[str]:
    pair = f"{currency}/RWF"
    if risk == "High":
        return [
            "If funds are available, consider paying the supplier earlier so a rate increase has less effect.",
            "If the invoice is large, consider splitting it into smaller payments instead of paying it all at once.",
            "Set aside extra money or adjust your selling price before confirming customer quotes.",
        ]
    if risk == "Medium":
        return [
            f"Check the {pair} rate again before the payment date.",
            "Set aside a small extra amount in case the foreign currency becomes more expensive.",
            "If the invoice is large, consider paying part of it earlier.",
        ]
    return [
        "Recent rates look fairly stable, but keep checking as the payment date approaches.",
        "The planned payment date appears reasonable based on recent rate changes.",
        "Check the rate again if the payment is delayed.",
    ]


def risk_pressure_rate(risk: str, horizon: int) -> float:
    # Conservative demo assumptions for cost-pressure scenarios.
    if risk == "High":
        return 0.012 if horizon == 7 else 0.02
    if risk == "Medium":
        return 0.006 if horizon == 7 else 0.012
    return 0.0025 if horizon == 7 else 0.005


def model_predict(currency: str, horizon: int):
    model = load_model(currency, horizon)
    try:
        row = latest_currency_feature_row(currency, FEATURE_COLUMNS)
    except (RuntimeError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    X = pd.DataFrame([row[FEATURE_COLUMNS].astype(float).to_dict()])
    pred = str(model.predict(X)[0])

    confidence = None
    predicted_probability = None
    top_probability_label = None
    probabilities = {}
    if hasattr(model, "predict_proba"):
        try:
            classes = list(model.classes_)
            probs = model.predict_proba(X)[0]
            probabilities = {str(cls): round(float(prob), 4) for cls, prob in zip(classes, probs)}
            top_probability_index = int(max(range(len(probs)), key=lambda i: probs[i]))
            top_probability_label = str(classes[top_probability_index])
            predicted_probability = round(float(probs[top_probability_index]), 4)
            confidence = predicted_probability
        except Exception:
            probabilities = {}
            confidence = None
            predicted_probability = None
            top_probability_label = None
    else:
        confidence = 1.0
        predicted_probability = 1.0
        top_probability_label = pred

    return pred, confidence, predicted_probability, top_probability_label, probabilities, row


@app.get("/")
def home():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "FXGuard AI API is running. Visit /docs for API documentation."}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "project": "FXGuard AI",
        "currencies": list(SUPPORTED_CURRENCIES),
        "pairs": [f"{currency}/RWF" for currency in SUPPORTED_CURRENCIES],
        "rate_provider": provider_status(),
    }


@app.get("/api/currencies")
def currencies():
    return {
        "base_currency": "RWF",
        "currencies": [
            {"code": code, "pair": f"{code}/RWF", **details}
            for code, details in CURRENCY_INFO.items()
        ],
    }


@app.get("/api/latest-rate")
def latest_rate(currency: str = "USD"):
    try:
        code = validate_currency(currency)
        df = combined_daily(code)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = df.iloc[-1]
    return {
        "date": str(row["date"].date()),
        "currency": code,
        "currency_name": CURRENCY_INFO[code]["name"],
        "currency_symbol": CURRENCY_INFO[code]["symbol"],
        "pair": f"{code}/RWF",
        "buying_rate": round(float(row["buying_rate"]), 4),
        "selling_rate": round(float(row["selling_rate"]), 4),
        "mid_rate": round(float(row["mid_rate"]), 4),
        "is_official_observation": bool(row.get("is_official_observation", 1)),
        "source": row.get("source", "National Bank of Rwanda Excel export"),
        "rate_type": row.get("rate_type", "BNR buying/average/selling rates"),
        "provider_status": provider_status(),
    }


@app.get("/api/latest-rates")
def latest_rates():
    return {
        "base_currency": "RWF",
        "rates": [latest_rate(currency) for currency in SUPPORTED_CURRENCIES],
    }


@app.get("/api/data-freshness")
def data_freshness(currency: str = "USD"):
    try:
        code = validate_currency(currency)
        daily = combined_daily(code)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    latest_rate_date = daily["date"].max().date()
    latest_feature_date = latest_currency_feature_row(code, FEATURE_COLUMNS)["date"].date()
    today = datetime.now().date()
    days_since_rate = max((today - latest_rate_date).days, 0)
    days_since_features = max((today - latest_feature_date).days, 0)

    if days_since_rate <= 5:
        status = "fresh"
    elif days_since_rate <= 30:
        status = "aging"
    else:
        status = "stale"

    return {
        "status": status,
        "currency": code,
        "pair": f"{code}/RWF",
        "today": str(today),
        "latest_rate_date": str(latest_rate_date),
        "latest_feature_date": str(latest_feature_date),
        "days_since_latest_rate": days_since_rate,
        "days_since_latest_features": days_since_features,
        "source": str(daily.iloc[-1].get("source", "National Bank of Rwanda Excel export")),
        "provider_status": provider_status(),
        "note": "Rates come from the latest manually imported official BNR Excel exports; import newer exports to refresh them.",
    }


@app.get("/api/history")
def history(days: int = 90, currency: str = "USD"):
    try:
        code = validate_currency(currency)
        df = combined_daily(code).tail(max(7, min(days, 1461)))
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "currency": code,
        "pair": f"{code}/RWF",
        "source": str(df.iloc[-1].get("source", "BNR reference-rate dataset")),
        "points": [
            {"date": str(r.date.date()), "mid_rate": round(float(r.mid_rate), 4)}
            for r in df.itertuples()
        ],
    }


@app.get("/api/model-metadata")
def model_metadata():
    return load_json(MODEL_DIR / "multicurrency_model_metadata.json")


@app.post("/api/predict-risk")
def predict_risk(req: RiskRequest):
    try:
        currency = validate_currency(req.currency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.horizon not in (7, 14):
        raise HTTPException(status_code=400, detail="Horizon must be 7 or 14 days.")

    risk, confidence, predicted_probability, top_probability_label, probabilities, row = model_predict(currency, req.horizon)
    current_rate = float(row["mid_rate"])
    current_cost = req.amount * current_rate
    pressure_rate = risk_pressure_rate(risk, req.horizon)
    possible_extra_cost = current_cost * pressure_rate
    suggested_buffer = current_cost * max(pressure_rate, 0.0025)

    return {
        "currency": currency,
        "currency_name": CURRENCY_INFO[currency]["name"],
        "currency_symbol": CURRENCY_INFO[currency]["symbol"],
        "pair": f"{currency}/RWF",
        "horizon_days": req.horizon,
        "amount": req.amount,
        "amount_currency": req.amount,
        "amount_usd": req.amount if currency == "USD" else None,
        "analysis_date": str(row["date"].date()),
        "current_rate": round(current_rate, 4),
        "current_cost_rwf": round(current_cost, 2),
        "risk_level": risk,
        "confidence": confidence,
        "confidence_score": confidence,
        "predicted_probability": predicted_probability,
        "top_probability_label": top_probability_label,
        "class_probabilities": probabilities,
        "probability_distribution": probabilities,
        "assumed_pressure_rate": pressure_rate,
        "possible_extra_cost_rwf": round(possible_extra_cost, 2),
        "suggested_margin_buffer_rwf": round(suggested_buffer, 2),
        "key_drivers": {
            "daily_return": round(float(row["daily_return"]), 6),
            "return_7d": round(float(row["return_7d"]), 6),
            "return_14d": round(float(row["return_14d"]), 6),
            "ma_7": round(float(row["ma_7"]), 4),
            "ma_30": round(float(row["ma_30"]), 4),
            "ma_gap": round(float(row["ma_gap"]), 6),
            "volatility_7d": round(float(row["volatility_7d"]), 6),
            "momentum_7d": round(float(row["momentum_7d"]), 6),
            "spread_pct": round(float(row["spread_pct"]), 6),
            "depreciation_days_7d": int(row["depreciation_days_7d"]),
        },
        "recommendations": risk_guidance(risk, currency),
        "rate_source": str(row.get("source", "BNR reference-rate dataset")),
        "rate_type": str(row.get("rate_type", "BNR reference rate")),
        "disclaimer": "FXGuard AI provides decision support only. It is not guaranteed financial, forex trading, or professional investment advice.",
    }


def build_excel_report(result: dict) -> BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Risk Assessment"
    sheet.sheet_view.showGridLines = False
    sheet.column_dimensions["A"].width = 36
    sheet.column_dimensions["B"].width = 74

    title_fill = PatternFill("solid", fgColor="1C3BAB")
    section_fill = PatternFill("solid", fgColor="DBE4FF")
    header_fill = PatternFill("solid", fgColor="EFF4FF")

    sheet.append(["FXGUARD AI — RISK ASSESSMENT REPORT"])
    sheet.merge_cells("A1:B1")
    sheet["A1"].fill = title_fill
    sheet["A1"].font = Font(color="FFFFFF", bold=True, size=15)
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 28

    def add_section(title: str, headings: tuple[str, str]) -> None:
        sheet.append([])
        sheet.append([title])
        row_number = sheet.max_row
        sheet.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=2)
        sheet.cell(row_number, 1).fill = section_fill
        sheet.cell(row_number, 1).font = Font(color="1C3BAB", bold=True)
        sheet.append(list(headings))
        for cell in sheet[sheet.max_row]:
            cell.fill = header_fill
            cell.font = Font(bold=True)

    amount = result.get("amount", result.get("amount_currency"))
    add_section("SUMMARY", ("Field", "Value"))
    summary_rows = [
        ("Date generated", datetime.now().strftime("%d %B %Y")),
        ("Analysis date (BNR data)", result["analysis_date"]),
        ("Currency pair", result["pair"]),
        (f"Payment amount ({result['currency']})", amount),
        ("Planning horizon (days)", result["horizon_days"]),
        (f"Current rate (RWF per {result['currency']})", result["current_rate"]),
        ("Risk level", result["risk_level"]),
        ("Strength of this result", result.get("confidence_score", result.get("confidence"))),
        ("Cost at current rate (RWF)", result["current_cost_rwf"]),
        ("Possible extra cost (RWF)", result["possible_extra_cost_rwf"]),
        ("Suggested safety buffer (RWF)", result["suggested_margin_buffer_rwf"]),
        ("Rate source", result["rate_source"]),
    ]
    for label, value in summary_rows:
        sheet.append([label, value])
    for row_number in range(7, sheet.max_row + 1):
        label = sheet.cell(row_number, 1).value
        value_cell = sheet.cell(row_number, 2)
        if label == "Strength of this result":
            value_cell.number_format = "0.0%"
        elif label and ("amount" in label.lower() or "rate" in label.lower() or "cost" in label.lower() or "buffer" in label.lower()):
            value_cell.number_format = "#,##0.00"

    add_section("HOW STRONGLY EACH RISK LEVEL IS SUPPORTED", ("Risk level", "Support"))
    for risk_class, probability in sorted(
        result.get("class_probabilities", {}).items(), key=lambda item: item[1], reverse=True
    ):
        sheet.append([risk_class, probability])
        sheet.cell(sheet.max_row, 2).number_format = "0.0%"

    add_section("RECOMMENDATIONS", ("#", "Action"))
    for index, recommendation in enumerate(result.get("recommendations", []), start=1):
        sheet.append([index, recommendation])
        sheet.cell(sheet.max_row, 2).alignment = Alignment(wrap_text=True, vertical="top")

    plain_driver_labels = {
        "daily_return": "Change since the previous day",
        "return_7d": "Change over the last 7 days",
        "return_14d": "Change over the last 14 days",
        "ma_7": "Typical rate over the last 7 days",
        "ma_30": "Typical rate over the last 30 days",
        "ma_gap": "Difference between recent and longer-term rates",
        "volatility_7d": "How much the rate moved up and down this week",
        "momentum_7d": "Direction the rate moved this week",
        "spread_pct": "Gap between BNR buying and selling rates",
        "depreciation_days_7d": "Days the foreign currency became more expensive this week",
    }
    percentage_drivers = {
        "daily_return", "return_7d", "return_14d", "ma_gap",
        "volatility_7d", "momentum_7d", "spread_pct",
    }

    add_section("WHAT THIS RESULT IS BASED ON", ("Recent rate information", "Value"))
    for signal, value in result.get("key_drivers", {}).items():
        if signal in percentage_drivers:
            display_value = f"{float(value) * 100:+.2f}%"
        elif signal in {"ma_7", "ma_30"}:
            display_value = f"{float(value):,.4f} RWF"
        elif signal == "depreciation_days_7d":
            display_value = f"{int(value)} of 7 days"
        else:
            display_value = value
        sheet.append([plain_driver_labels.get(signal, signal.replace("_", " ").title()), display_value])

    add_section("IMPORTANT NOTE", ("Notice", "Details"))
    sheet.append(["Decision support only", result["disclaimer"]])
    sheet.cell(sheet.max_row, 2).alignment = Alignment(wrap_text=True, vertical="top")

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


@app.post("/api/export-excel")
def export_excel(req: RiskRequest):
    result = predict_risk(req)
    output = build_excel_report(result)
    filename = f"fxguard-result-{result['analysis_date']}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    feedback_data = req.model_dump()
    feedback_data["submitted_at"] = datetime.now().isoformat(timespec="seconds")
    row = pd.DataFrame([feedback_data], columns=FEEDBACK_COLUMNS)

    if FEEDBACK_FILE.exists():
        existing = pd.read_excel(FEEDBACK_FILE, dtype={"phone_number": str})
        combined = pd.concat([existing, row], ignore_index=True)
    else:
        combined = row

    combined = combined.reindex(columns=FEEDBACK_COLUMNS)
    combined.to_excel(FEEDBACK_FILE, index=False)
    google_sheet_result = append_feedback_to_google_sheet(feedback_data)
    return {
        "status": "saved",
        "message": "Thank you for your feedback.",
        "file": project_path_label(FEEDBACK_FILE),
        "google_sheet": google_sheet_result,
    }


@app.get("/api/feedback-file")
def download_feedback_file():
    if not FEEDBACK_FILE.exists():
        raise HTTPException(status_code=404, detail="No feedback responses have been saved yet.")
    return FileResponse(
        FEEDBACK_FILE,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=FEEDBACK_FILE.name,
    )
