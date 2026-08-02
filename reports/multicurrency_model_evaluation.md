# FXGuard AI Multicurrency Model Evaluation

Generated: 2026-08-02T10:13:13+00:00

Each candidate is evaluated with three expanding-window rolling-origin folds inside the first 80% of the history. The selected model is then evaluated once on the untouched final 20% holdout.

Any training row whose future outcome date reaches a test window is removed so labels derived from future rates cannot cross the boundary.
After model selection and holdout evaluation, the selected production model is refitted on all labeled observations.

## USD/RWF

### 7-day horizon

- Selected model: `logistic_regression`
- Final training window: 2022-02-16 to 2025-08-25 (859 rows)
- Untouched holdout: 2025-09-02 to 2026-07-20 (217 rows)
- Production refit: 2022-02-16 to 2026-07-20 (1081 rows)
- Outcome-date purge: 5 official observations removed at the final holdout boundary
- Reliability status: `experimental_not_trustworthy`
- Most-frequent baseline: balanced accuracy 0.3333, macro F1 0.2468
- Mean backtest metrics: accuracy 0.5463, balanced accuracy 0.4949, macro F1 0.3585
- Final holdout metrics: accuracy 1.0000, balanced accuracy unavailable, macro F1 1.0000

Rolling-origin folds:

- Fold 1: train through 2024-04-19; test 2024-04-29 to 2024-10-08; purged 5 boundary observations; balanced accuracy 0.5966; macro F1 0.4280
- Fold 2: train through 2024-10-01; test 2024-10-09 to 2025-03-14; purged 5 boundary observations; balanced accuracy 0.3864; macro F1 0.3596
- Fold 3: train through 2025-03-07; test 2025-03-17 to 2025-09-01; purged 5 boundary observations; balanced accuracy 0.5017; macro F1 0.2878

### 14-day horizon

- Selected model: `logistic_regression`
- Final training window: 2022-02-16 to 2025-08-12 (851 rows)
- Untouched holdout: 2025-08-27 to 2026-07-13 (216 rows)
- Production refit: 2022-02-16 to 2026-07-13 (1076 rows)
- Outcome-date purge: 9 official observations removed at the final holdout boundary
- Reliability status: `experimental_not_trustworthy`
- Most-frequent baseline: balanced accuracy 0.3889, macro F1 0.2804
- Mean backtest metrics: accuracy 0.5189, balanced accuracy 0.5648, macro F1 0.3504
- Final holdout metrics: accuracy 1.0000, balanced accuracy unavailable, macro F1 1.0000

Rolling-origin folds:

- Fold 1: train through 2024-04-09; test 2024-04-25 to 2024-10-03; purged 10 boundary observations; balanced accuracy 0.6275; macro F1 0.3731
- Fold 2: train through 2024-09-19; test 2024-10-04 to 2025-03-11; purged 10 boundary observations; balanced accuracy 0.5652; macro F1 0.3980
- Fold 3: train through 2025-02-25; test 2025-03-12 to 2025-08-26; purged 10 boundary observations; balanced accuracy 0.5017; macro F1 0.2802

## EUR/RWF

### 7-day horizon

- Selected model: `random_forest`
- Final training window: 2022-02-16 to 2025-08-25 (859 rows)
- Untouched holdout: 2025-09-02 to 2026-07-20 (217 rows)
- Production refit: 2022-02-16 to 2026-07-20 (1081 rows)
- Outcome-date purge: 5 official observations removed at the final holdout boundary
- Reliability status: `experimental_not_trustworthy`
- Most-frequent baseline: balanced accuracy 0.3333, macro F1 0.2069
- Mean backtest metrics: accuracy 0.4506, balanced accuracy 0.3667, macro F1 0.2981
- Final holdout metrics: accuracy 0.5576, balanced accuracy 0.3492, macro F1 0.3049

Rolling-origin folds:

- Fold 1: train through 2024-04-19; test 2024-04-29 to 2024-10-08; purged 5 boundary observations; balanced accuracy 0.3529; macro F1 0.2370
- Fold 2: train through 2024-10-01; test 2024-10-09 to 2025-03-14; purged 5 boundary observations; balanced accuracy 0.4036; macro F1 0.3777
- Fold 3: train through 2025-03-07; test 2025-03-17 to 2025-09-01; purged 5 boundary observations; balanced accuracy 0.3435; macro F1 0.2797

### 14-day horizon

- Selected model: `xgboost`
- Final training window: 2022-02-16 to 2025-08-12 (851 rows)
- Untouched holdout: 2025-08-27 to 2026-07-13 (216 rows)
- Production refit: 2022-02-16 to 2026-07-13 (1076 rows)
- Outcome-date purge: 9 official observations removed at the final holdout boundary
- Reliability status: `experimental_not_trustworthy`
- Most-frequent baseline: balanced accuracy 0.3333, macro F1 0.2115
- Mean backtest metrics: accuracy 0.3823, balanced accuracy 0.3520, macro F1 0.2189
- Final holdout metrics: accuracy 0.7222, balanced accuracy 0.3685, macro F1 0.3564

Rolling-origin folds:

- Fold 1: train through 2024-04-09; test 2024-04-25 to 2024-10-03; purged 10 boundary observations; balanced accuracy 0.3684; macro F1 0.2461
- Fold 2: train through 2024-09-19; test 2024-10-04 to 2025-03-11; purged 10 boundary observations; balanced accuracy 0.3543; macro F1 0.2013
- Fold 3: train through 2025-02-25; test 2025-03-12 to 2025-08-26; purged 10 boundary observations; balanced accuracy 0.3333; macro F1 0.2094

## KES/RWF

### 7-day horizon

- Selected model: `logistic_regression`
- Final training window: 2022-02-16 to 2025-08-25 (859 rows)
- Untouched holdout: 2025-09-02 to 2026-07-20 (217 rows)
- Production refit: 2022-02-16 to 2026-07-20 (1081 rows)
- Outcome-date purge: 5 official observations removed at the final holdout boundary
- Reliability status: `experimental_not_trustworthy`
- Most-frequent baseline: balanced accuracy 0.3333, macro F1 0.0791
- Mean backtest metrics: accuracy 0.5062, balanced accuracy 0.3722, macro F1 0.2268
- Final holdout metrics: accuracy 0.5069, balanced accuracy 0.3333, macro F1 0.2243

Rolling-origin folds:

- Fold 1: train through 2024-04-19; test 2024-04-29 to 2024-10-08; purged 5 boundary observations; balanced accuracy 0.4500; macro F1 0.1338
- Fold 2: train through 2024-10-01; test 2024-10-09 to 2025-03-14; purged 5 boundary observations; balanced accuracy 0.3333; macro F1 0.2529
- Fold 3: train through 2025-03-07; test 2025-03-17 to 2025-09-01; purged 5 boundary observations; balanced accuracy 0.3333; macro F1 0.2936

### 14-day horizon

- Selected model: `xgboost`
- Final training window: 2022-02-16 to 2025-08-12 (851 rows)
- Untouched holdout: 2025-08-27 to 2026-07-13 (216 rows)
- Production refit: 2022-02-16 to 2026-07-13 (1076 rows)
- Outcome-date purge: 9 official observations removed at the final holdout boundary
- Reliability status: `experimental_not_trustworthy`
- Most-frequent baseline: balanced accuracy 0.3333, macro F1 0.0534
- Mean backtest metrics: accuracy 0.3535, balanced accuracy 0.3900, macro F1 0.2315
- Final holdout metrics: accuracy 0.3843, balanced accuracy 0.3341, macro F1 0.2220

Rolling-origin folds:

- Fold 1: train through 2024-04-09; test 2024-04-25 to 2024-10-03; purged 10 boundary observations; balanced accuracy 0.3411; macro F1 0.0886
- Fold 2: train through 2024-09-19; test 2024-10-04 to 2025-03-11; purged 10 boundary observations; balanced accuracy 0.4024; macro F1 0.3593
- Fold 3: train through 2025-02-25; test 2025-03-12 to 2025-08-26; purged 10 boundary observations; balanced accuracy 0.4266; macro F1 0.2465
