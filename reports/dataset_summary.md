# FXGuard Prepared BNR Exchange Rate Dataset — 4-Year Daily Version

This package was created from the uploaded BNR export: `currency_table.xlsx`.

## Coverage

- Raw date range: **2022-01-04 to 2026-06-25**
- Prepared 4-year period: **2022-06-26 to 2026-06-25**
- Currency/currencies found: **USD**
- Official BNR observations in 4-year period: **978**
- Daily calendar rows after forward-fill: **1,461**
- Model-ready 7-day rows: **1,425**
- Model-ready 14-day rows: **1,418**

## Files

| File | Purpose |
|---|---|
| `data/raw/currency_table.xlsx` | Original uploaded BNR Excel export. |
| `data/processed/bnr_official_observations_4year.csv` | Clean official BNR records inside the 4-year period. |
| `data/processed/exchange_rates_daily_calendar_4year.csv` | Full daily calendar with weekends/non-posting days forward-filled. |
| `data/processed/exchange_rates_features_and_labels_4year.csv` | Feature-engineered dataset with 7-day and 14-day future risk labels. |
| `data/processed/exchange_rates_model_ready_7d_4year.csv` | Final 7-day model-training dataset. |
| `data/processed/exchange_rates_model_ready_14d_4year.csv` | Final 14-day model-training dataset. |
| `data_dictionary.csv` | Explanation of columns. |
| `dataset_summary.json` | Machine-readable summary. |

## Risk Label Method

Risk labels are created from future depreciation of the RWF against the selected foreign currency.
If the exchange rate increases, more RWF is needed to buy one unit of the foreign currency, meaning RWF depreciation.

Quantile thresholds were used:

| Horizon | Low / Medium boundary | Medium / High boundary |
|---|---:|---:|
| 7-day | 0.0015660065 | 0.0026750329 |
| 14-day | 0.0031488225 | 0.0053906120 |

Interpretation:

- Low risk: future depreciation is in the lower 50% of historical observations.
- Medium risk: future depreciation is between the 50th and 80th percentile.
- High risk: future depreciation is in the top 20% of historical observations.

## Important Note

The uploaded file contains **USD only**. To build the full multi-currency FXGuard system, export and prepare the same period for EUR, GBP, KES, UGX, CNY, and any other currencies you want to support.
