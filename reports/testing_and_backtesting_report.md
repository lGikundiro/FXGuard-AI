# FXGuard AI Multicurrency Testing and Backtesting Report

## Report purpose

This section explains how FXGuard AI was tested, what the results mean, and what conclusions can reasonably be drawn from them. It is written for a non-technical audience while retaining the technical details needed for an academic report.

The project used two different forms of testing:

1. **Software testing** checked whether the application, API, data-processing functions, account controls, and backtesting logic behaved as designed.
2. **Model backtesting** checked how well the machine-learning models would have performed on historical periods they had not yet seen.

These tests answer different questions. Passing the software tests shows that the system functions correctly. It does not automatically mean that every model prediction will be accurate.

## Executive summary

FXGuard AI passed all **35 automated software tests**. The tests covered exchange-rate data preparation, supplementary-workbook merging, multicurrency API responses, feedback mapping and Excel backup, model outputs, backtesting safeguards, frontend structure, and account security controls.

The forecasting models were evaluated separately for USD/RWF, EUR/RWF, and KES/RWF over 7-day and 14-day horizons. For each of these six forecasting tasks, Logistic Regression, Random Forest, and XGBoost were compared using three rolling historical test periods.

The USD models achieved the strongest rolling-backtest results, although their performance was still moderate rather than highly accurate. The EUR and KES results were generally close to the one-third balanced-accuracy reference point for a three-class problem. This means that the models should be presented as experimental decision-support tools, not as guaranteed forecasts.

The backtesting also revealed an important limitation that a single train/test split had hidden: the most recent USD holdout period contained only Low-risk observations. A model could therefore obtain 100% accuracy in that period simply by predicting Low every time. The rolling backtests provide a more realistic assessment because they include historical periods with a wider mixture of Low, Medium, and High risk.

## Automated software testing

The complete automated test suite was run on 27 July 2026 with the following command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result:

```text
Ran 35 tests
OK
```

All 35 tests passed. The coverage was:

| Test area | Number of tests | What was checked |
|---|---:|---|
| Account and security foundations | 11 | Explicit CORS origins, CSRF protection, user-owned database records, safe session cookies, consent records, validation of saved results, legal acknowledgement, provider capability enforcement, secure URL validation, and self-service account deletion |
| Frontend structure | 9 | Unique HTML element IDs, valid account-script references, required account/legal screens, native feedback form structure, light-mode persistence, consent validation, and correct script-loading order |
| Model behavior | 2 | Human-readable Low/Medium/High outputs and availability of all three candidate algorithms |
| Multicurrency API | 6 | USD/EUR/KES support, rate history, predictions, invalid-currency rejection, valid Excel report generation, feedback-to-Google-Form field mapping, and local Excel feedback backup |
| Backtesting safeguards | 3 | Forward-only historical folds, 7/14-day purge gaps, metric aggregation, and rejection of folds that enter the final holdout |
| Data synchronization | 4 | Valid official BNR histories, supplementary-file discovery and merging, common updated coverage, and prevention of invented records before a currency's first observation |
| **Total** | **35** | **All passed** |

These results show that the tested software paths behave as expected. They do not replace penetration testing, a full security audit, legal review, real-user acceptance testing, or monitoring under production traffic.

## Why historical backtesting was needed

A foreign-exchange model must be tested in time order. Randomly mixing old and new records could allow information from the future to influence a model that is supposed to predict that future. This would make the reported performance look better than it really is.

FXGuard AI therefore uses **rolling-origin backtesting**, also called walk-forward validation. In simple terms, the model is trained on an earlier period and tested on the period immediately after it. The training period is then expanded, and the process is repeated.

The approach simulates the question:

> If the system had existed at that point in history and knew only the information available then, how well would it have classified the following period?

## Backtesting design

The testing procedure was applied independently to all six forecasting tasks:

- USD/RWF over 7 days
- USD/RWF over 14 days
- EUR/RWF over 7 days
- EUR/RWF over 14 days
- KES/RWF over 7 days
- KES/RWF over 14 days

The 7-day datasets contained 1,629 labeled daily observations per currency. The 14-day datasets contained 1,622 labeled daily observations per currency. The model-ready period began on 3 February 2022 and extended to 20 July 2026 for the 7-day models and 13 July 2026 for the 14-day models.

For each task, three candidate algorithms were tested:

- **Logistic Regression:** a simpler and more interpretable statistical classifier.
- **Random Forest:** a collection of decision trees that can represent nonlinear patterns.
- **XGBoost:** a boosted-tree algorithm designed to learn more complex relationships.

Three expanding historical folds were used inside the first 80% of the dataset:

| Fold | Earlier observations used for training | Following observations used for testing |
|---|---:|---:|
| 1 | Approximately the first 50% | The next 10% |
| 2 | Approximately the first 60% | The next 10% |
| 3 | Approximately the first 70% | The next 10% |

The final 20% of the history was kept separate as a holdout. It was not used to choose the winning algorithm.

### Protection against future-information leakage

The historical risk label for a date is calculated using the exchange rate 7 or 14 days later. Without an extra safeguard, the final labels in a training period could indirectly contain information from the following test period.

To prevent this, FXGuard AI removes a boundary gap between training and testing:

- 7 rows for a 7-day forecast
- 14 rows for a 14-day forecast

This is known as a **purge gap**. It ensures that a training label cannot look ahead into the period being tested.

### Model selection and final training

The mean rolling backtest results were used to choose the model. Balanced accuracy was the primary selection measure, followed by Macro F1 and ordinary accuracy.

After model selection, the chosen model was evaluated on the untouched final holdout. Only after recording those results was the production model refitted using all available labeled observations. This allows the live application to benefit from the latest training data without using the final holdout to choose the algorithm.

## Meaning of the evaluation measures

Three measures were reported:

- **Accuracy** is the percentage of all observations classified correctly. It can be misleading when one class is much more common than the others.
- **Balanced accuracy** gives equal importance to Low, Medium, and High risk. In a three-class problem, a value near 0.333 indicates that the model has limited ability to distinguish the three classes evenly.
- **Macro F1** combines precision and recall and gives equal importance to each risk class. A low Macro F1 indicates that at least some classes are being identified poorly.

Balanced accuracy and Macro F1 are particularly important for FXGuard AI because the classes are not evenly distributed across every historical period.

## Rolling backtest results

The table below reports the mean across the three historical folds for the selected algorithm.

| Currency pair | Horizon | Selected model | Accuracy | Balanced accuracy | Macro F1 |
|---|---:|---|---:|---:|---:|
| USD/RWF | 7 days | Logistic Regression | 0.5113 | 0.4682 | 0.3874 |
| USD/RWF | 14 days | Logistic Regression | 0.5638 | 0.4081 | 0.3733 |
| EUR/RWF | 7 days | Random Forest | 0.4397 | 0.3743 | 0.2960 |
| EUR/RWF | 14 days | Logistic Regression | 0.3580 | 0.3532 | 0.2717 |
| KES/RWF | 7 days | Random Forest | 0.3211 | 0.3746 | 0.2386 |
| KES/RWF | 14 days | Logistic Regression | 0.4506 | 0.3756 | 0.2389 |

### Plain-language interpretation

**USD/RWF:** The 7-day USD model produced the strongest rolling balanced accuracy, at 0.4682. This shows that it learned some useful historical separation between the three risk classes, but the performance is not strong enough to treat an individual prediction as certain. The 14-day model achieved higher ordinary accuracy but lower balanced accuracy, meaning its correct predictions were not spread evenly across Low, Medium, and High risk.

**EUR/RWF:** The 7-day Random Forest was the best EUR candidate, but its balanced accuracy of 0.3743 was only modestly above the one-third reference point. The 14-day EUR result was also close to that reference point. The current features therefore provide limited evidence of reliable EUR risk-class separation.

**KES/RWF:** Random Forest is now selected for the 7-day KES task, while Logistic Regression remains selected for 14 days. Their rolling balanced accuracies were similar, and their low Macro F1 scores show that performance remained uneven across the three classes.

**Overall:** Logistic Regression was selected for four of the six tasks, while Random Forest was selected for EUR and KES over 7 days. XGBoost did not produce the best average balanced accuracy for any task. This suggests that additional algorithm complexity did not solve the main challenge, which is extracting stable short-term predictive patterns from the available historical features.

## Final holdout results

The selected models were also evaluated on the final 20% of observations, which had not been used for model selection.

| Currency pair | Horizon | Holdout accuracy | Holdout balanced accuracy | Holdout Macro F1 |
|---|---:|---:|---:|---:|
| USD/RWF | 7 days | 1.0000 | Unavailable | 1.0000 |
| USD/RWF | 14 days | 1.0000 | Unavailable | 1.0000 |
| EUR/RWF | 7 days | 0.5184 | 0.3525 | 0.2833 |
| EUR/RWF | 14 days | 0.6154 | 0.3526 | 0.3201 |
| KES/RWF | 7 days | 0.4479 | 0.4188 | 0.3340 |
| KES/RWF | 14 days | 0.4246 | 0.3333 | 0.1987 |

The USD holdout scores require special caution. All 326 observations in the 7-day USD holdout and all 325 observations in the 14-day USD holdout were labeled Low risk. Balanced accuracy could not be calculated because Medium and High risk were absent. The 100% accuracy therefore shows that the model correctly identified that stable period, but it does not prove that the model can distinguish all three risk levels.

The EUR and KES holdouts contained all three classes, making them more informative about class separation. Their balanced accuracies were close to one-third, which confirms that the present models have limited predictive strength across the three risk levels.

## What the testing demonstrates

The testing supports the following conclusions:

1. The multicurrency application and its main software controls work correctly under the 35 automated test cases.
2. The backtesting process respects time order and includes safeguards against future-information leakage.
3. The rolling evaluation gives a more honest performance estimate than the earlier single holdout result.
4. The USD models show some historical predictive signal, particularly over 7 days.
5. The EUR and KES models currently show weak separation between Low, Medium, and High risk.
6. The output is suitable for experimental decision support and academic demonstration, but not for guaranteed financial forecasting.

## Limitations and recommended next steps

The following limitations should be stated in the overall report:

- Historical performance does not guarantee future performance.
- The models use exchange-rate history and engineered technical features; they do not yet include inflation, interest rates, trade flows, market news, or other macroeconomic variables.
- Some test periods contain imbalanced risk classes, especially the USD final holdout.
- Three rolling folds give a better view than one split, but more historical regimes and future unseen observations would strengthen the evidence.
- Risk labels are based on thresholds calculated from the available history. These thresholds may need periodic review as currency behavior changes.
- The probability shown by the application should be treated as a model score, not as a guaranteed real-world probability.

Recommended future improvements are:

1. Add more recent BNR observations and repeat the backtest on a scheduled basis.
2. Monitor live predictions against the outcomes observed 7 or 14 days later.
3. Add macroeconomic and market-context features where reliable official data is available.
4. Investigate probability calibration and class-specific error analysis.
5. Compare model performance against simple baselines, such as always predicting the most common class or continuing the latest trend.
6. Define a minimum acceptable performance threshold before presenting the system as production-ready.

## Report-ready conclusion

FXGuard AI was evaluated using automated software tests and time-aware model backtesting. All 35 software tests passed, confirming that the tested data, API, model, frontend, account-security, feedback, and backtesting functions behaved as designed. The machine-learning evaluation used three expanding rolling-origin folds for each currency and prediction horizon, with purge gaps to prevent future-derived labels from leaking into training. A separate final holdout was excluded from model selection.

The results were mixed. USD/RWF showed the strongest rolling historical performance, with a 7-day balanced accuracy of 0.4682, while EUR/RWF and KES/RWF generally remained close to the one-third reference point for three-class classification. The perfect USD holdout accuracy was caused by a test period containing only Low-risk observations and was therefore not treated as proof of perfect forecasting. These findings support the use of FXGuard AI as a transparent experimental decision-support prototype, while also showing that further data, feature development, calibration, and ongoing validation are necessary before operational financial reliance.

## Presentation-ready slide

### Model and system testing

- **35 automated software tests passed**
- Tested USD, EUR, and KES over **7-day and 14-day horizons**
- Compared **Logistic Regression, Random Forest, and XGBoost**
- Used **three forward-only rolling historical folds**
- Added **7/14-day purge gaps** to prevent future-data leakage
- Kept the final **20% as an independent holdout**
- Best rolling result: **USD 7-day balanced accuracy = 46.82%**
- EUR and KES remained close to the **33.3% three-class reference point**
- Conclusion: useful as an **experimental decision-support prototype**, not a guaranteed forecast

### Suggested speaker notes

> We tested both whether the software works and whether the models can classify unseen historical periods. All 35 automated software tests passed. For model testing, we trained on earlier dates and tested on later dates three times, without randomly mixing the timeline. We also removed a boundary gap to prevent future information from entering training. The USD 7-day model showed the strongest rolling result, while EUR and KES were close to the three-class reference level. The testing therefore supports FXGuard AI as a functioning and transparent prototype, but not as a guaranteed forecasting system.

## Supporting project evidence

- Detailed fold results: `reports/multicurrency_model_evaluation.md`
- Machine-readable metrics: `backend/models/multicurrency_model_metadata.json`
- Backtesting implementation: `scripts/train_multicurrency_models.py`
- Automated backtesting tests: `tests/test_multicurrency_backtesting.py`
- Other automated tests: `tests/test_accounts.py`, `tests/test_frontend_structure.py`, `tests/test_modeling.py`, `tests/test_multicurrency_api.py`, and `tests/test_multicurrency_sync.py`
