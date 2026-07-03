# FXGuard AI — USD-RWF Exchange Rate Risk Forecasting MVP

FXGuard AI is a full-stack web application integrated with machine learning models for classifying short-term USD/RWF depreciation risk for Rwanda-based importers.

The MVP focuses on **USD-RWF only** using a prepared 4-year BNR dataset. The architecture is designed so that EUR, GBP, KES, UGX, CNY, and other currencies can be added later using the same data-preparation pipeline.

Deployed link to project: https://fxguard-ai.onrender.com/

## What the project includes

- 4-year USD/RWF dataset prepared from BNR export
- Feature-engineered datasets for 7-day and 14-day risk labels
- Trained ML models for 7-day and 14-day risk classification
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
    models/                      # trained risk models and metadata
  data/
    raw/currency_table.xlsx      # original uploaded BNR Excel export
    processed/                   # clean, feature, and model-ready datasets
    data_dictionary.csv
  frontend/index.html            # web UI markup
  frontend/styles.css            # frontend styling
  frontend/app.js                # frontend behavior and API calls
  scripts/train_models.py        # retrain ML models
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

## Model details

The current MVP trains two models:

- `risk_model_7d.pkl` — predicts 7-day USD/RWF depreciation risk
- `risk_model_14d.pkl` — predicts 14-day USD/RWF depreciation risk
- The current training script compares logistic regression, random forest, and XGBoost.

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
python scripts/train_models.py
```

This will recreate:

```text
backend/models/risk_model_7d.pkl
backend/models/risk_model_14d.pkl
backend/models/model_metadata.json
```

The saved model files will contain the best-performing classifier for each horizon after the comparison run.

The training script also regenerates:

```text
reports/model_evaluation.md
```

This report records the chronological train/test windows, class distributions, majority-class baseline, rolling-origin backtest folds, probability-quality metrics, and any warnings about class imbalance in the validation windows.

Current model-validation caveat: the most recent chronological test windows contain only the `Low` risk class, so perfect-looking accuracy should be interpreted carefully. The rolling-origin backtest in `reports/model_evaluation.md` gives a more honest view of performance across earlier windows where more classes appear.

If `xgboost` is not installed in the active Python environment, the training script skips XGBoost and records that in the model metadata/report instead of failing.

## Main API endpoints

```text
GET  /health
GET  /api/latest-rate
GET  /api/data-freshness
GET  /api/history?days=180
GET  /api/model-metadata
POST /api/predict-risk
POST /api/feedback
GET  /api/feedback-file
```

Example prediction request:

```json
{
  "currency": "USD",
  "amount": 10000,
  "horizon": 7,
  "margin_percent": 20
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

The current app uses local prepared BNR datasets. The `/api/data-freshness` endpoint reports how many days old the latest local rate and feature rows are. A future production version should automatically fetch new official BNR exchange-rate data, rebuild processed datasets, retrain or validate the models, and publish a fresh evaluation report.

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
