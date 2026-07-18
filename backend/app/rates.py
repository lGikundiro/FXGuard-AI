"""Access the bundled exchange rates imported from official BNR Excel exports."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "processed" / "multicurrency_daily_calendar.csv"
METADATA_PATH = ROOT / "data" / "processed" / "multicurrency_data_metadata.json"

CURRENCY_INFO = {
    "USD": {"name": "US Dollar", "symbol": "$", "display_decimals": 2},
    "EUR": {"name": "Euro", "symbol": "\u20ac", "display_decimals": 2},
    "KES": {"name": "Kenyan Shilling", "symbol": "KSh", "display_decimals": 4},
}
SUPPORTED_CURRENCIES = tuple(CURRENCY_INFO)

_local_daily: pd.DataFrame | None = None


def validate_currency(currency: str) -> str:
    code = currency.strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        supported = ", ".join(SUPPORTED_CURRENCIES)
        raise ValueError(f"Unsupported currency {code!r}. Choose one of: {supported}.")
    return code


def load_local_daily() -> pd.DataFrame:
    global _local_daily
    if _local_daily is None:
        if not DATA_PATH.exists():
            raise FileNotFoundError(f"Multi-currency dataset is missing: {DATA_PATH}")
        frame = pd.read_csv(DATA_PATH, parse_dates=["date"])
        frame["currency"] = frame["currency"].str.upper()
        missing = set(SUPPORTED_CURRENCIES) - set(frame["currency"].unique())
        if missing:
            raise ValueError(f"Processed BNR data is missing currencies: {', '.join(sorted(missing))}.")
        _local_daily = frame.loc[frame["currency"].isin(SUPPORTED_CURRENCIES)].sort_values(
            ["currency", "date"]
        ).reset_index(drop=True)
    return _local_daily.copy()


def combined_daily(currency: str, allow_live: bool = True) -> pd.DataFrame:
    """Return the imported BNR history for one currency on a daily calendar.

    ``allow_live`` remains in the signature for compatibility with older callers.
    No network source is used; data changes only after importing new BNR workbooks.
    """
    del allow_live
    code = validate_currency(currency)
    selected = load_local_daily()
    selected = selected.loc[selected["currency"] == code].copy()
    if selected.empty:
        raise RuntimeError(f"No imported BNR rates are available for {code}.")
    return selected.reset_index(drop=True)


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values("date").copy()
    result["daily_return"] = result["mid_rate"].pct_change(fill_method=None)
    result["return_7d"] = result["mid_rate"].pct_change(7, fill_method=None)
    result["return_14d"] = result["mid_rate"].pct_change(14, fill_method=None)
    result["ma_7"] = result["mid_rate"].rolling(7).mean()
    result["ma_14"] = result["mid_rate"].rolling(14).mean()
    result["ma_30"] = result["mid_rate"].rolling(30).mean()
    result["ma_gap"] = result["ma_7"] / result["ma_30"] - 1
    result["volatility_7d"] = result["daily_return"].rolling(7).std()
    result["volatility_14d"] = result["daily_return"].rolling(14).std()
    result["volatility_30d"] = result["daily_return"].rolling(30).std()
    result["momentum_7d"] = result["return_7d"]
    result["momentum_14d"] = result["return_14d"]
    result["spread"] = result["selling_rate"] - result["buying_rate"]
    result["spread_pct"] = result["spread"] / result["mid_rate"]
    depreciated = (result["daily_return"] > 0).astype(int)
    result["depreciation_days_7d"] = depreciated.rolling(7).sum()
    result["depreciation_days_14d"] = depreciated.rolling(14).sum()
    return result


def latest_feature_row(currency: str, feature_columns: list[str]) -> pd.Series:
    features = add_features(combined_daily(currency))
    ready = features.dropna(subset=feature_columns)
    if ready.empty:
        raise RuntimeError(f"No complete feature row is available for {currency}.")
    return ready.iloc[-1]


def provider_status() -> dict:
    metadata = {}
    if METADATA_PATH.exists():
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    coverage = metadata.get("coverage", {})
    latest_dates = [item.get("latest_date") for item in coverage.values() if item.get("latest_date")]
    return {
        "live_enabled": False,
        "provider": "National Bank of Rwanda",
        "delivery_mode": metadata.get("delivery_mode", "manual official export"),
        "source_url": metadata.get("source_url", "https://www.bnr.rw/exchangeRate"),
        "last_imported_rate_date": max(latest_dates) if latest_dates else None,
        "currencies": list(SUPPORTED_CURRENCIES),
        "last_error": None,
    }
