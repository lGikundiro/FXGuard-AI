"""Build the three-currency model datasets from direct BNR Excel exports."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DATA_DIR = ROOT / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BNR_SOURCE_URL = "https://www.bnr.rw/exchangeRate"
RAW_FILES = {
    "USD": RAW_DIR / "USD exchange history.xlsx",
    "EUR": RAW_DIR / "Euro exchange history.xlsx",
    "KES": RAW_DIR / "KES exchange hsitroy.xlsx",
}
CURRENCIES = tuple(RAW_FILES)
RAW_COLUMNS = {"currency_name", "buying_rate", "average_rate", "selling_rate", "post_date"}
ADDITIONAL_FILE_PATTERN = re.compile(
    r"^(USD|EUR|KES) additional "
    r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\.xlsx$",
    re.IGNORECASE,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_raw_workbook(currency: str, path: Path) -> pd.DataFrame:
    """Load and strictly validate one unmodified BNR currency-history workbook."""
    if not path.exists():
        raise FileNotFoundError(f"Raw {currency} workbook is missing: {path}")

    raw = pd.read_excel(path)
    missing = RAW_COLUMNS - set(raw.columns)
    if missing:
        raise RuntimeError(f"{path.name} is missing required columns: {sorted(missing)}")

    observed_currencies = set(raw["currency_name"].dropna().astype(str).str.strip().str.upper())
    if observed_currencies != {currency}:
        raise RuntimeError(
            f"{path.name} should contain only {currency}; found {sorted(observed_currencies)}"
        )

    result = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["post_date"], format="%d-%b-%y", errors="coerce"),
            "currency": currency,
        }
    )
    for column in ("buying_rate", "average_rate", "selling_rate"):
        result[column] = pd.to_numeric(
            raw[column].astype(str).str.replace(",", "", regex=False), errors="coerce"
        )

    required = ["date", "buying_rate", "average_rate", "selling_rate"]
    invalid = result[required].isna().any(axis=1)
    if invalid.any():
        raise RuntimeError(f"{path.name} contains {int(invalid.sum())} invalid date/rate rows.")
    if result["date"].duplicated().any():
        raise RuntimeError(f"{path.name} contains duplicate observation dates.")
    if (result[["buying_rate", "average_rate", "selling_rate"]] <= 0).any().any():
        raise RuntimeError(f"{path.name} contains non-positive exchange rates.")
    invalid_order = (
        (result["buying_rate"] > result["average_rate"])
        | (result["average_rate"] > result["selling_rate"])
    )
    if invalid_order.any():
        raise RuntimeError(f"{path.name} contains rates outside buying <= average <= selling.")

    result["mid_rate"] = result["average_rate"]
    result["is_official_observation"] = 1
    result["source"] = "National Bank of Rwanda Excel export"
    result["rate_type"] = "BNR buying/average/selling rates"
    return result.sort_values("date").reset_index(drop=True)


def discover_raw_files() -> dict[str, list[Path]]:
    """Return each baseline workbook plus strictly named supplementary exports."""
    discovered = {currency: [path] for currency, path in RAW_FILES.items()}
    for path in sorted(RAW_DIR.glob("*.xlsx")):
        if "additional" not in path.name.lower():
            continue
        match = ADDITIONAL_FILE_PATTERN.fullmatch(path.name)
        if not match:
            raise RuntimeError(
                f"Additional workbook has an invalid filename: {path.name}. "
                "Use '<CURRENCY> additional YYYY-MM-DD to YYYY-MM-DD.xlsx'."
            )
        currency = match.group(1).upper()
        discovered[currency].append(path)
    return discovered


def load_currency_observations(currency: str, paths: list[Path]) -> pd.DataFrame:
    """Validate and merge all official workbooks for one currency."""
    frames = []
    for path in paths:
        frame = load_raw_workbook(currency, path)
        match = ADDITIONAL_FILE_PATTERN.fullmatch(path.name)
        if match:
            filename_start = pd.Timestamp(match.group(2))
            filename_end = pd.Timestamp(match.group(3))
            content_start = frame["date"].min()
            content_end = frame["date"].max()
            if filename_start != content_start or filename_end != content_end:
                raise RuntimeError(
                    f"{path.name} says {filename_start.date()} to {filename_end.date()}, "
                    f"but its content covers {content_start.date()} to {content_end.date()}."
                )
        frame["_raw_file"] = path.name
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    duplicate_dates = combined.loc[
        combined["date"].duplicated(keep=False), ["date", "_raw_file"]
    ].sort_values(["date", "_raw_file"])
    if not duplicate_dates.empty:
        details = "; ".join(
            f"{observed_date.date()}: {', '.join(group['_raw_file'].tolist())}"
            for observed_date, group in duplicate_dates.groupby("date")
        )
        raise RuntimeError(f"{currency} source workbooks contain duplicate dates: {details}")
    return combined.drop(columns="_raw_file").sort_values("date").reset_index(drop=True)


def load_direct_observations(
    source_files: dict[str, list[Path]] | None = None,
) -> pd.DataFrame:
    source_files = source_files or discover_raw_files()
    frames = [
        load_currency_observations(currency, source_files[currency])
        for currency in CURRENCIES
    ]
    ranges = {
        (str(frame["date"].min().date()), str(frame["date"].max().date()))
        for frame in frames
    }
    if len(ranges) != 1:
        raise RuntimeError(f"The BNR workbooks do not use the same date range: {sorted(ranges)}")
    return pd.concat(frames, ignore_index=True).sort_values(["currency", "date"]).reset_index(drop=True)


def build_daily_calendar(observations: pd.DataFrame) -> pd.DataFrame:
    frames = []
    available = set(observations["currency"].dropna().astype(str).str.upper())
    for currency in (code for code in CURRENCIES if code in available):
        source = observations.loc[observations["currency"] == currency].copy()
        calendar = pd.DataFrame(
            {"date": pd.date_range(source["date"].min(), source["date"].max(), freq="D")}
        )
        merged = calendar.merge(source, on="date", how="left")
        merged["currency"] = currency
        merged["is_official_observation"] = merged["is_official_observation"].fillna(0).astype(int)
        for column in (
            "buying_rate", "average_rate", "selling_rate", "mid_rate", "source", "rate_type"
        ):
            merged[column] = merged[column].ffill().bfill()
        frames.append(merged)
    if not frames:
        raise ValueError("No supported currency observations were provided.")
    return pd.concat(frames, ignore_index=True).sort_values(["currency", "date"]).reset_index(drop=True)


def add_features(group: pd.DataFrame) -> pd.DataFrame:
    """Create predictors from real BNR postings only.

    Rolling windows count official observations, not forward-filled calendar rows.
    This prevents weekends and non-posting days from being learned as artificial
    zero-return observations.
    """
    frame = group.sort_values("date").copy()
    frame["observation_gap_days"] = frame["date"].diff().dt.days
    frame["daily_return"] = frame["mid_rate"].pct_change(fill_method=None)
    frame["return_7d"] = frame["mid_rate"].pct_change(7, fill_method=None)
    frame["return_14d"] = frame["mid_rate"].pct_change(14, fill_method=None)
    frame["ma_7"] = frame["mid_rate"].rolling(7).mean()
    frame["ma_14"] = frame["mid_rate"].rolling(14).mean()
    frame["ma_30"] = frame["mid_rate"].rolling(30).mean()
    frame["ma_gap"] = frame["ma_7"] / frame["ma_30"] - 1
    frame["volatility_7d"] = frame["daily_return"].rolling(7).std()
    frame["volatility_14d"] = frame["daily_return"].rolling(14).std()
    frame["volatility_30d"] = frame["daily_return"].rolling(30).std()
    frame["momentum_7d"] = frame["return_7d"]
    frame["momentum_14d"] = frame["return_14d"]
    frame["spread"] = frame["selling_rate"] - frame["buying_rate"]
    frame["spread_pct"] = frame["spread"] / frame["mid_rate"]
    depreciated = (frame["daily_return"] > 0).astype(int)
    frame["depreciation_days_7d"] = depreciated.rolling(7).sum()
    frame["depreciation_days_14d"] = depreciated.rolling(14).sum()
    for horizon in (7, 14):
        lookup = frame[["date", "mid_rate"]].rename(
            columns={"date": f"future_{horizon}d_date", "mid_rate": f"future_{horizon}d_rate"}
        )
        targets = frame[["date"]].copy()
        targets["target_date"] = targets["date"] + pd.Timedelta(days=horizon)
        matched = pd.merge_asof(
            targets.sort_values("target_date"),
            lookup.sort_values(f"future_{horizon}d_date"),
            left_on="target_date",
            right_on=f"future_{horizon}d_date",
            direction="forward",
        ).sort_values("date")
        frame[f"future_{horizon}d_date"] = matched[f"future_{horizon}d_date"].to_numpy()
        frame[f"future_{horizon}d_change"] = (
            matched[f"future_{horizon}d_rate"].to_numpy() / frame["mid_rate"].to_numpy() - 1
        )
    return frame


def add_currency_labels(features: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    labelled = features.copy()
    thresholds: dict[str, dict[str, float]] = {}
    for currency in CURRENCIES:
        mask = labelled["currency"] == currency
        thresholds[currency] = {}
        for horizon in (7, 14):
            future_column = f"future_{horizon}d_change"
            label_column = f"risk_label_{horizon}d"
            values = labelled.loc[mask, future_column]
            valid = values.dropna()
            low_threshold = float(valid.quantile(0.50))
            high_threshold = float(valid.quantile(0.80))
            labels = np.select(
                [values <= low_threshold, values <= high_threshold],
                ["Low", "Medium"],
                default="High",
            ).astype(object)
            labels[values.isna().to_numpy()] = np.nan
            labelled.loc[mask, label_column] = labels
            thresholds[currency][f"{horizon}d_low_max"] = low_threshold
            thresholds[currency][f"{horizon}d_medium_max"] = high_threshold
    return labelled, thresholds


def main() -> None:
    source_files = discover_raw_files()
    observations = load_direct_observations(source_files)
    # The calendar series remains available for charts. Model features are built
    # only from official postings so forward-filled weekends cannot distort them.
    daily = build_daily_calendar(observations)
    features = pd.concat(
        [add_features(observations.loc[observations["currency"] == currency]) for currency in CURRENCIES],
        ignore_index=True,
    )
    features, thresholds = add_currency_labels(features)

    observations.to_csv(DATA_DIR / "multicurrency_bnr_observations.csv", index=False)
    daily.to_csv(DATA_DIR / "multicurrency_daily_calendar.csv", index=False)
    features.to_csv(DATA_DIR / "multicurrency_features_and_labels.csv", index=False)

    feature_columns = [
        "mid_rate", "daily_return", "return_7d", "return_14d", "ma_7", "ma_14", "ma_30",
        "ma_gap", "volatility_7d", "volatility_14d", "volatility_30d", "momentum_7d",
        "momentum_14d", "spread", "spread_pct", "depreciation_days_7d", "depreciation_days_14d",
    ]
    for horizon in (7, 14):
        label_column = f"risk_label_{horizon}d"
        future_column = f"future_{horizon}d_change"
        future_date_column = f"future_{horizon}d_date"
        model_ready = features.dropna(subset=feature_columns + [label_column]).copy()
        model_ready[[
            "date", "currency", *feature_columns, future_date_column, future_column, label_column
        ]].to_csv(
            DATA_DIR / f"multicurrency_model_ready_{horizon}d.csv", index=False
        )

    coverage = {
        currency: {
            "first_date": str(group["date"].min().date()),
            "latest_date": str(group["date"].max().date()),
            "official_observations": int(group["is_official_observation"].sum()),
            "source": "National Bank of Rwanda Excel export",
        }
        for currency, group in observations.groupby("currency")
    }
    metadata = {
        "generated_at": date.today().isoformat(),
        "source": "Direct National Bank of Rwanda Excel exports",
        "source_url": BNR_SOURCE_URL,
        "delivery_mode": "manual official export",
        "currencies": list(CURRENCIES),
        "coverage": coverage,
        "first_date": str(observations["date"].min().date()),
        "latest_date": str(observations["date"].max().date()),
        "label_thresholds": thresholds,
        "model_preprocessing": {
            "training_rows": "official BNR observations only",
            "calendar_series_use": "display only; forward-filled dates are excluded from model training",
            "forecast_horizons": "calendar days; the first official posting on or after the target date supplies the outcome",
            "rolling_window_unit": "official observations",
        },
    }
    metadata["raw_files"] = {
        currency: [
            {
                "filename": path.name,
                "sha256": file_sha256(path),
                "rows": int(len(frame)),
                "first_date": str(frame["date"].min().date()),
                "latest_date": str(frame["date"].max().date()),
            }
            for path in paths
            for frame in [load_raw_workbook(currency, path)]
        ]
        for currency, paths in source_files.items()
    }
    (DATA_DIR / "multicurrency_data_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
