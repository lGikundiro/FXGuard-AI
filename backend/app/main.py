from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
    description="USD/RWF exchange-rate risk forecasting and decision-support API for Rwanda-based importers.",
    version="1.0.0",
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
    currency: str = Field(default="USD", description="Currency code. MVP supports USD only.")
    amount: float = Field(default=10000, gt=0, description="Supplier invoice amount in USD.")
    horizon: int = Field(default=7, description="Prediction horizon in days: 7 or 14.")
    margin_percent: Optional[float] = Field(default=None, ge=0, le=100, description="Optional target margin.")


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


def load_model(horizon: int):
    if horizon not in (7, 14):
        raise HTTPException(status_code=400, detail="Horizon must be 7 or 14 days.")
    key = f"model_{horizon}d"
    if key not in _cache:
        path = MODEL_DIR / f"risk_model_{horizon}d.pkl"
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


def risk_guidance(risk: str) -> List[str]:
    if risk == "High":
        return [
            "Consider paying the supplier earlier if cash flow allows.",
            "Consider splitting the payment to reduce exposure.",
            "Review selling prices or add a margin buffer before confirming quotes.",
        ]
    if risk == "Medium":
        return [
            "Monitor the USD/RWF rate closely before the payment date.",
            "Review pricing assumptions and prepare a small margin buffer.",
            "Consider partial payment if the invoice is large.",
        ]
    return [
        "Risk is currently low; continue monitoring normally.",
        "The current payment timing appears manageable based on recent signals.",
        "Review again if the payment date is delayed.",
    ]


def risk_pressure_rate(risk: str, horizon: int) -> float:
    # Conservative demo assumptions for cost-pressure scenarios.
    if risk == "High":
        return 0.012 if horizon == 7 else 0.02
    if risk == "Medium":
        return 0.006 if horizon == 7 else 0.012
    return 0.0025 if horizon == 7 else 0.005


def model_predict(horizon: int):
    model = load_model(horizon)
    row = latest_feature_row()
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
    return {"status": "ok", "project": "FXGuard AI", "currency_pair": "USD/RWF"}


@app.get("/api/latest-rate")
def latest_rate():
    df = load_daily_calendar()
    row = df.iloc[-1]
    return {
        "date": str(row["date"].date()),
        "currency": row["currency"],
        "buying_rate": round(float(row["buying_rate"]), 4),
        "selling_rate": round(float(row["selling_rate"]), 4),
        "mid_rate": round(float(row["mid_rate"]), 4),
        "is_official_observation": bool(row.get("is_official_observation", 1)),
    }


@app.get("/api/data-freshness")
def data_freshness():
    daily = load_daily_calendar()
    features = load_features()
    latest_rate_date = daily["date"].max().date()
    latest_feature_date = features["date"].max().date()
    today = datetime.now().date()
    days_since_rate = max((today - latest_rate_date).days, 0)
    days_since_features = max((today - latest_feature_date).days, 0)

    if days_since_rate <= 2:
        status = "fresh"
    elif days_since_rate <= 14:
        status = "aging"
    else:
        status = "stale"

    return {
        "status": status,
        "today": str(today),
        "latest_rate_date": str(latest_rate_date),
        "latest_feature_date": str(latest_feature_date),
        "days_since_latest_rate": days_since_rate,
        "days_since_latest_features": days_since_features,
        "source": "Local prepared BNR dataset",
        "note": "Refresh the processed datasets and retrain models when new official rates are available.",
    }


@app.get("/api/history")
def history(days: int = 90):
    df = load_daily_calendar().tail(max(7, min(days, 1461)))
    return {
        "currency": "USD",
        "pair": "USD/RWF",
        "points": [
            {"date": str(r.date.date()), "mid_rate": round(float(r.mid_rate), 4)}
            for r in df.itertuples()
        ],
    }


@app.get("/api/model-metadata")
def model_metadata():
    return load_json(MODEL_DIR / "model_metadata.json")


@app.post("/api/predict-risk")
def predict_risk(req: RiskRequest):
    if req.currency.upper() != "USD":
        raise HTTPException(status_code=400, detail="This MVP supports USD/RWF only. Other currencies are future enhancements.")
    if req.horizon not in (7, 14):
        raise HTTPException(status_code=400, detail="Horizon must be 7 or 14 days.")

    risk, confidence, predicted_probability, top_probability_label, probabilities, row = model_predict(req.horizon)
    current_rate = float(row["mid_rate"])
    current_cost = req.amount * current_rate
    pressure_rate = risk_pressure_rate(risk, req.horizon)
    possible_extra_cost = current_cost * pressure_rate
    suggested_buffer = current_cost * max(pressure_rate, 0.0025)

    return {
        "currency": "USD",
        "pair": "USD/RWF",
        "horizon_days": req.horizon,
        "amount_usd": req.amount,
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
        "recommendations": risk_guidance(risk),
        "disclaimer": "FXGuard AI provides decision support only. It is not guaranteed financial, forex trading, or professional investment advice.",
    }


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
