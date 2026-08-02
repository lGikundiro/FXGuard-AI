# FXGuard AI Flexible-Horizon Testing and Backtesting Report

## Executive summary

FXGuard AI now asks when the invoice will be paid instead of offering fixed 7-day and 14-day buttons. The client and API allow a payment date from tomorrow through 100 days from the current date. The API calculates `horizon_days` and supplies it to a horizon-aware classifier for USD/RWF, EUR/RWF, or KES/RWF.

All **42 automated software tests passed**. The tests cover data preparation, official-observation features, 1–100-day dataset construction, time-aware purging, training-only thresholds, reliability gates, API date limits, predictions, exports, frontend structure, accounts, and security foundations.

Predictive reliability remains limited. None of the three flexible models passes the project-defined reliability gate. The system must therefore remain an experimental decision-support prototype, and its displayed percentages are approximate uncalibrated model scores rather than verified probabilities.

## Product behavior

The payment-check workflow is now:

1. The user chooses USD, EUR, or KES and enters the invoice amount.
2. The user selects the intended payment date.
3. The browser permits dates from tomorrow through 100 days ahead.
4. The API independently recalculates and validates the number of days, preventing bypass of the browser limit.
5. The selected currency's flexible model receives the latest rate features plus `horizon_days`.
6. The result preserves both `payment_date` and `horizon_days` in saved checks and exports.

The current model does not recursively reuse a 7-day or 14-day prediction. It was retrained with outcomes for every integer horizon from 1 to 100 days, so the requested period is part of the supervised learning problem.

## Flexible-horizon dataset

For each official BNR observation date and each integer horizon from 1 to 100 days, the training pipeline finds the first official rate posting on or after the calendar target date. It calculates the future percentage change and retains `horizon_days` as a predictor.

Approximate supervised-row totals are:

| Currency | Rows | Horizon values |
|---|---:|---:|
| USD/RWF | 105,240 | 100 |
| EUR/RWF | 105,240 | 100 |
| KES/RWF | 105,240 | 100 |

Weekend and non-posting rows are not model observations. The forward-filled daily calendar remains display-only.

## Leakage safeguards

Evaluation uses observation dates rather than randomly splitting the expanded rows. All horizon variants for a date therefore remain on the same side of a split.

Before a fold is trained, any row whose future outcome date reaches the following test period is removed. Because the longest supported invoice period is 100 days, this can create a boundary purge of up to 100 calendar days.

Low, Medium, and High thresholds are calculated separately for every horizon using the earlier training dates only. The evaluation period cannot influence the thresholds used to define its labels.

## Reliability gate

A model passes only if it meets all three project-defined conditions:

- Mean balanced accuracy of at least 0.55
- Mean Macro F1 of at least 0.45
- Balanced-accuracy improvement of at least 0.05 over a most-frequent-class baseline

These are transparent research thresholds, not universal financial-industry standards.

## Rolling backtest results

| Pair | Selected model | Accuracy | Balanced accuracy | Macro F1 | Status |
|---|---|---:|---:|---:|---|
| USD/RWF | Logistic Regression | 0.6386 | 0.4472 | 0.2801 | Experimental; gate failed |
| EUR/RWF | XGBoost | 0.3084 | 0.2987 | 0.1680 | Experimental; gate failed |
| KES/RWF | Random Forest | 0.4982 | 0.4016 | 0.2470 | Experimental; gate failed |

The USD ordinary accuracy is relatively high because some historical periods are dominated by one risk class. Balanced accuracy and Macro F1 show that performance remains uneven across Low, Medium, and High. EUR and KES also fail to demonstrate reliable class separation.

## Final holdout results

| Pair | Accuracy | Balanced accuracy | Macro F1 |
|---|---:|---:|---:|
| USD/RWF | 1.0000 | Unavailable | 1.0000 |
| EUR/RWF | 0.8164 | 0.3667 | 0.3646 |
| KES/RWF | 0.2481 | 0.3329 | 0.1326 |

The final USD holdout contains only Low labels across its usable horizon/date combinations. Its perfect accuracy is therefore not evidence that the model distinguishes all three classes. Detailed 1–14, 15–30, 31–60, and 61–100-day holdout results are generated in `reports/flexible_horizon_model_evaluation.md`.

## Approximation sign and score meaning

The main result displays a value such as `≈ 72%`. The approximation sign is intentional. The value is the largest score produced by the selected classifier, but calibration has not established that a displayed 72% corresponds to the outcome occurring 72 times out of 100.

The same approximate wording is used in downloadable HTML and Excel reports. The interface also states whether the model passed the reliability gate; all current models are marked experimental.

## Automated testing

Run the complete suite with:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Current result:

```text
Ran 42 tests
OK
```

The test suite includes explicit checks that:

- The flexible dataset contains horizons 1 and 100.
- A training outcome never crosses into its test period.
- Horizon thresholds come only from training rows.
- Tomorrow and day 100 are supported by the production models.
- Today/past dates and day 101 are rejected by the API.
- The fixed horizon buttons are absent from the interface.
- The browser configures a maximum date of today plus 100 days.
- The model-score output includes the `≈` sign.
- Saved checks preserve the payment date.

## Defense-ready conclusion

FXGuard AI now aligns the user workflow with real invoice planning: users enter the date on which they expect to pay, and the system calculates a supported 1–100-day horizon. The underlying models were retrained across the full horizon range, and evaluation uses date-grouped rolling folds, horizon-specific training thresholds, and outcome-date purging to prevent leakage. All 42 software tests pass. However, none of the flexible models passes the declared reliability gate, so the correct claim remains that FXGuard AI is a functioning experimental decision-support prototype whose predictive reliability requires further improvement and prospective validation.

## Presentation-ready slide

- User selects the actual invoice payment date
- Browser and API enforce **1–100 days**
- One horizon-aware model per currency
- Training includes every integer horizon from **1 through 100**
- Date-grouped rolling backtesting with up to a **100-day purge**
- Training-only Low/Medium/High thresholds for every horizon
- **42 automated tests passed**
- Scores display with `≈` because they are uncalibrated
- No flexible model passes the reliability gate yet
- Conclusion: functional experimental prototype, not a trustworthy financial forecast
