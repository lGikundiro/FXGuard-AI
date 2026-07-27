# FXGuard AI — Multi-currency Exchange Rate Risk Forecasting

FXGuard AI is a full-stack web application with machine-learning models for classifying short-term foreign-currency/RWF depreciation risk for Rwanda-based importers.

The prototype supports **USD, EUR, and KES against RWF**. Each currency has its own 7-day and 14-day classifier trained on official BNR exchange-rate history.

Fast-loading interface: https://fxguard-ai-web.onrender.com/

API and fallback interface: https://fxguard-ai.onrender.com/
YouTube Demo: https://youtu.be/jNrEOB-uwfE

## What the project includes

- Official BNR buying, average, and selling rates imported from Excel exports
- More than four years of USD/RWF, EUR/RWF, and KES/RWF history
- Per-currency feature datasets and trained 7-day/14-day classifiers
- FastAPI backend
- Web interface frontend
- Decision-support output for importers
- Optional phone or email accounts using one-time verification codes
- User-owned cloud history, account export, check deletion, and account deletion
- Plain-language Privacy Notice and Terms of Use
- Feedback form for usability testing
- Training script to retrain the models

## Project structure

```text
FXGuard_AI_Project/
  backend/
    app/main.py                  # FastAPI backend
    models/                      # per-currency risk models and metadata
  data/
    raw/                         # uploaded BNR histories for USD, EUR, and KES
    processed/                   # clean, feature, and model-ready datasets
    data_dictionary.csv
  frontend/index.html            # web UI markup
  frontend/styles.css            # frontend styling
  frontend/app.js                # frontend behavior and API calls
  frontend/accounts.js           # account, consent, and cloud-history behavior
  supabase/migrations/           # PostgreSQL tables and row-level access policies
  scripts/sync_multicurrency_rates.py   # refresh rate histories/features
  scripts/train_multicurrency_models.py # retrain all currency models
  reports/                       # dataset summaries and user feedback output
  render.yaml                    # Render deployment blueprint
  requirements.txt
  run_backend.py
  run_windows.bat
  run_mac_linux.sh
```

## How to run in VS Code

### 1. Open the folder

Open `FXGuard_AI_Project` in VS Code.

### 2. Create a virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Mac/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the app

Option A:

```bash
python run_backend.py
```

Option B:

```bash
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Option C in VS Code:

- Open **Run and Debug**
- Select **Run FXGuard API**
- Click the green run button

### 5. Open the web app

Visit:

```text
http://127.0.0.1:8000
```

API docs are available at:

```text
http://127.0.0.1:8000/docs
```

## Configure accounts and saved checks

Guest payment checks work without a database. Phone/email accounts and cross-device history use Supabase Auth and PostgreSQL.

1. Create a Supabase project.
2. Open **SQL Editor** and run the SQL files in `supabase/migrations/` in numeric order.
3. In **Authentication > Providers**, enable email and phone authentication.
4. Configure a supported SMS provider for phone codes.
5. Change the Supabase email template to show `{{ .Token }}` so users receive an email code instead of only a link.
6. Copy `.env.example` values into the local shell or the Render service environment.

Required server environment variables:

```text
SUPABASE_URL
SUPABASE_PUBLISHABLE_KEY
AUTH_METHODS
ALLOWED_ORIGINS
AUTH_COOKIE_SECURE
```

Optional server variables:

```text
SUPABASE_DB_URL
SUPABASE_SERVICE_ROLE_KEY
AUTH_SELF_DELETE_RPC
```

`SUPABASE_URL` must be the HTTPS project API URL, such as `https://your-project.supabase.co`, not a PostgreSQL connection string. Store an optional database connection separately as `SUPABASE_DB_URL`.

`AUTH_METHODS` is a comma-separated list of providers that are already enabled in Supabase Auth. The current configuration uses `email`; add `phone` only after configuring an SMS provider.

Apply both SQL files in `supabase/migrations/`. Migration `002_self_service_account_deletion.sql` enables narrowly scoped self-service account deletion without exposing an administrative key. `SUPABASE_SERVICE_ROLE_KEY` remains an optional server-only administrative fallback; never add it to `frontend/`, source control, screenshots, or browser configuration.

For local PowerShell, set the values for the current terminal before starting the app:

```powershell
$env:SUPABASE_URL="https://your-project.supabase.co"
$env:SUPABASE_PUBLISHABLE_KEY="your-publishable-key"
$env:SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
$env:AUTH_METHODS="email"
$env:ALLOWED_ORIGINS="http://127.0.0.1:8000,http://localhost:8000"
$env:AUTH_COOKIE_SECURE="false"
python run_backend.py
```

Production sessions use secure `HttpOnly` cookies and CSRF protection. For the static frontend and API, use custom subdomains under the same registered domain (for example `app.example.com` and `api.example.com`) to avoid third-party-cookie restrictions. Set both origins in `ALLOWED_ORIGINS` and update `window.FXGUARD_API_URL` in the static build configuration.

Before enabling real accounts, complete the required Rwanda data-controller/processor and external-storage review. The in-app Privacy Notice and Terms are product drafts and require qualified legal review.

## Deploy on Render

This project is configured for Render with `render.yaml`.

1. Push the project to GitHub.
2. In Render, choose **New > Blueprint** or **New > Web Service**.
3. Connect the GitHub repository.
4. If using the dashboard manually, use:

```text
Build Command:
pip install -r requirements.txt

Start Command:
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT

Health Check Path:
/health
```

The deployment uses Python `3.12.10` from `.python-version`. The Blueprint also deploys the frontend as a Render Static Site. This lets the interface load from Render's CDN immediately while the free API service wakes in the background. The Python service still serves a fallback copy of the interface.

## Rate data source

Bundled historical USD, EUR, and KES data comes exclusively from the official BNR Excel exports in `data/raw/`. Their published buying, average, and selling rates are retained, and the average rate is used as the model's `mid_rate`.

The application does not synthesize rates or fetch them through a third-party provider. It serves the most recently imported official records and clearly reports their date through `/api/data-freshness`.

To refresh the data, download the new USD, EUR, and KES records from BNR's exchange-rate page and keep the original history workbooks unchanged. Save each supplementary export in `data/raw/` as `<CURRENCY> additional YYYY-MM-DD to YYYY-MM-DD.xlsx`, using `EUR`, `USD`, or `KES` and the exact first and last dates inside the workbook. Then run the synchronization and training commands below. The synchronization script discovers all supplementary files, validates their currency codes, columns, rates, filename date ranges, overlaps, and workbook hashes, and merges them chronologically before producing application data.

## Model details

The prototype trains two models for each supported currency:

- `risk_model_<CURRENCY>_7d.pkl` — classifies 7-day depreciation pressure
- `risk_model_<CURRENCY>_14d.pkl` — classifies 14-day depreciation pressure
- Training compares logistic regression, random forest, and XGBoost for every currency/horizon.

Risk classes:

- Low
- Medium
- High

Features used:

- `mid_rate`
- `daily_return`
- `return_7d`
- `return_14d`
- `ma_7`
- `ma_14`
- `ma_30`
- `ma_gap`
- `volatility_7d`
- `volatility_14d`
- `volatility_30d`
- `momentum_7d`
- `momentum_14d`
- `spread`
- `spread_pct`
- `depreciation_days_7d`
- `depreciation_days_14d`

## Retrain the models

```bash
python scripts/sync_multicurrency_rates.py
python scripts/train_multicurrency_models.py
```

This validates the three official BNR Excel histories and recreates the multi-currency datasets, six model files, and:

```text
backend/models/multicurrency_model_metadata.json
```

The metadata records each chronological train/test window, class distribution, candidate metrics, selected classifier, data date, and per-currency label thresholds. Treat the likelihood probability as a decision-support signal: it is not a guarantee of the future exchange rate, and some recent validation windows have limited class variety.

Model selection uses three expanding-window rolling-origin backtest folds for every currency and horizon. These folds stay within the first 80% of the history, while the final 20% remains an untouched holdout. A 7-row or 14-row purge gap separates each training and test window to prevent future-derived labels from crossing the evaluation boundary. After evaluation, the selected production model is refitted on all labeled observations. Detailed results are written to `reports/multicurrency_model_evaluation.md`.

Current testing documentation:

- `reports/multicurrency_model_evaluation.md` — generated fold-by-fold multicurrency metrics
- `reports/testing_and_backtesting_report.md` — plain-language technical report, conclusion, and presentation summary
- `reports/README.md` — report index distinguishing current evidence from preserved USD-only material

## Main API endpoints

```text
GET  /health
GET  /api/currencies
GET  /api/latest-rate?currency=EUR
GET  /api/latest-rates
GET  /api/data-freshness?currency=KES
GET  /api/history?currency=USD&days=180
GET  /api/model-metadata
POST /api/predict-risk
POST /api/export-excel
POST /api/feedback
GET  /api/feedback-file
```

Example prediction request:

```json
{
  "currency": "EUR",
  "amount": 10000,
  "horizon": 7
}
```

## Important academic note

The system provides **decision support only**. It does not provide financial advice, forex trading advice, or professional consultancy. Exchange-rate movements are uncertain, and the tool should be considered alongside the user's own business information when making major decisions.

## User testing

For research evaluation, the app provides a native HTML/CSS/JavaScript form on the **Share feedback** page.

Form link:

```text
https://docs.google.com/forms/d/e/1FAIpQLSd3E97VFGFl7v-9ojSAAmPc4RkE-30tf9YCJ_XUhPuw8JFbBg/viewform
```

The form sends validated responses to the backend. The backend saves a local Excel backup and forwards the same fields to the existing Google Forms response spreadsheet:

```text
POST /api/feedback
GET  /api/feedback-file
```

The default Google Form response destination is configured through `GOOGLE_FORM_RESPONSE_URL` in `.env.example`. The native form preserves the response sheet's existing columns for timestamp, clarity, usefulness, comments, participant name, import category, and phone number.

Participants should use hypothetical supplier amounts during testing unless they voluntarily choose otherwise. The project does not collect bank details, supplier contracts, real financial statements, or confidential business records.


## Improvement roadmap

The app reports the age of its latest imported BNR record through `/api/data-freshness`. A production deployment should establish a documented schedule for downloading the official BNR exports, running `sync_multicurrency_rates.py`, and retraining or validating the models after enough new observations accumulate. Direct BNR API access could automate that workflow later if it becomes available.

The frontend is still a single-file MVP, but the most immediate bugs have been cleaned: duplicate recommendation container IDs were removed, the obsolete hidden feedback controls were removed, and the feedback flow now uses a native accessible form backed by the API and existing response sheet.


## Notebooks

The overview notebook describes the current multicurrency system. Notebooks `01` through `05` preserve the guided **original USD/RWF workflow** used during early project development. They are useful for explaining the data-science steps, but they do not train the active multicurrency production artifacts. Use `scripts/sync_multicurrency_rates.py` and `scripts/train_multicurrency_models.py` for the current USD/EUR/KES system.

1. `00_project_overview.ipynb` — current USD/EUR/KES product, data, model, API, account, and deployment overview
2. `01_data_collection_and_cleaning.ipynb` — load BNR Excel export and clean USD/RWF rates
3. `02_feature_engineering_and_labels.ipynb` — create ML features and 7-day/14-day risk labels
4. `03_model_training_and_evaluation.ipynb` — train and evaluate the original USD/RWF models
5. `04_prediction_function_and_api_test.ipynb` — test prediction logic and API request structure
6. `05_user_testing_and_evaluation.ipynb` — organize usability testing and feedback analysis

To open them in VS Code, install the Python and Jupyter extensions, then open any `.ipynb` file from the notebooks folder.
