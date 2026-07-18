# FXGuard AI — Multi-currency Exchange Rate Risk Forecasting

FXGuard AI is a full-stack web application with machine-learning models for classifying short-term foreign-currency/RWF depreciation risk for Rwanda-based importers.

The prototype supports **USD, EUR, and KES against RWF**. Each currency has its own 7-day and 14-day classifier trained on official BNR exchange-rate history.

Deployed link to project: https://fxguard-ai.onrender.com/
YouTube Demo: https://youtu.be/jNrEOB-uwfE

## What the project includes

- Official BNR buying, average, and selling rates imported from Excel exports
- More than four years of USD/RWF, EUR/RWF, and KES/RWF history
- Per-currency feature datasets and trained 7-day/14-day classifiers
- FastAPI backend
- Web interface frontend
- Decision-support output for importers
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

The deployment uses Python `3.12.10` from `.python-version`. The app serves both the FastAPI backend and the frontend from one Render Web Service.

## Rate data source

Bundled historical USD, EUR, and KES data comes exclusively from the official BNR Excel exports in `data/raw/`. Their published buying, average, and selling rates are retained, and the average rate is used as the model's `mid_rate`.

The application does not synthesize rates or fetch them through a third-party provider. It serves the most recently imported official records and clearly reports their date through `/api/data-freshness`.

To refresh the data, download updated USD, EUR, and KES histories from BNR's exchange-rate page, replace the three workbooks in `data/raw/`, and run the synchronization and training commands below. The synchronization script validates codes, columns, dates, rates, and workbook hashes before producing application data.

## Model details

The prototype trains two models for each supported currency:

- `risk_model_<CURRENCY>_7d.pkl` — classifies 7-day depreciation pressure
- `risk_model_<CURRENCY>_14d.pkl` — classifies 14-day depreciation pressure
- Training compares logistic regression and random forest for every currency/horizon.

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

The metadata records each chronological train/test window, class distribution, candidate metrics, selected classifier, data date, and per-currency label thresholds. Treat model confidence as a decision-support signal: it is not a guarantee of the future exchange rate, and some recent validation windows have limited class variety.

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

The system provides **decision support only**. It is not guaranteed financial advice, forex trading advice, or professional consultancy. Exchange-rate movements are uncertain, and users should not rely only on the tool for major business decisions.

## User testing

For research evaluation, the app embeds the Google Form named `FXGuard AI User feedback` in the **Participant feedback** page.

Form link:

```text
https://docs.google.com/forms/d/e/1FAIpQLSd3E97VFGFl7v-9ojSAAmPc4RkE-30tf9YCJ_XUhPuw8JFbBg/viewform
```

Users submit feedback through the embedded Google Form. Responses are saved directly in the Google Forms response spreadsheet connected to that form. If the embedded form does not load in a browser, users can click **Open form in new tab** on the feedback page.

The backend still includes the local feedback API and Excel download endpoint as a backup:

```text
POST /api/feedback
GET  /api/feedback-file
```

Participants should use hypothetical supplier amounts during testing unless they voluntarily choose otherwise. The project does not collect bank details, supplier contracts, real financial statements, or confidential business records.


## Improvement roadmap

The app reports the age of its latest imported BNR record through `/api/data-freshness`. A production deployment should establish a documented schedule for downloading the official BNR exports, running `sync_multicurrency_rates.py`, and retraining or validating the models after enough new observations accumulate. Direct BNR API access could automate that workflow later if it becomes available.

The frontend is still a single-file MVP, but the most immediate bugs have been cleaned: duplicate recommendation container IDs were removed, the obsolete hidden feedback controls were removed, and the visible feedback flow now uses the embedded Google Form.


## Notebooks

The `notebooks/` folder contains guided Jupyter notebooks for the full data science workflow:

1. `00_project_overview.ipynb` — project structure and workflow overview
2. `01_data_collection_and_cleaning.ipynb` — load BNR Excel export and clean USD/RWF rates
3. `02_feature_engineering_and_labels.ipynb` — create ML features and 7-day/14-day risk labels
4. `03_model_training_and_evaluation.ipynb` — train and evaluate baseline + ML models
5. `04_prediction_function_and_api_test.ipynb` — test prediction logic and API request structure
6. `05_user_testing_and_evaluation.ipynb` — organize usability testing and feedback analysis

To open them in VS Code, install the Python and Jupyter extensions, then open any `.ipynb` file from the notebooks folder.
