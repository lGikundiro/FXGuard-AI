# FXGuard AI Multicurrency Model Evaluation

Generated: 2026-07-27T11:06:17+00:00

Each candidate is evaluated with three expanding-window rolling-origin folds inside the first 80% of the history. The selected model is then evaluated once on the untouched final 20% holdout.

A horizon-length purge gap is removed between every training and test window so labels derived from future rates cannot cross the boundary.
After model selection and holdout evaluation, the selected production model is refitted on all labeled observations.

## USD/RWF

### 7-day horizon

- Selected model: `logistic_regression`
- Final training window: 2022-02-03 to 2025-08-21 (1296 rows)
- Untouched holdout: 2025-08-29 to 2026-07-20 (326 rows)
- Production refit: 2022-02-03 to 2026-07-20 (1629 rows)
- Purge gap: 7 rows
- Mean backtest metrics: accuracy 0.5113, balanced accuracy 0.4682, macro F1 0.3874
- Final holdout metrics: accuracy 1.0000, balanced accuracy unavailable, macro F1 1.0000

Rolling-origin folds:

- Fold 1: train through 2024-04-19; test 2024-04-27 to 2024-10-06; balanced accuracy 0.4639; macro F1 0.4444
- Fold 2: train through 2024-09-29; test 2024-10-07 to 2025-03-18; balanced accuracy 0.4263; macro F1 0.4187
- Fold 3: train through 2025-03-11; test 2025-03-19 to 2025-08-28; balanced accuracy 0.5144; macro F1 0.2991

### 14-day horizon

- Selected model: `logistic_regression`
- Final training window: 2022-02-03 to 2025-08-08 (1283 rows)
- Untouched holdout: 2025-08-23 to 2026-07-13 (325 rows)
- Production refit: 2022-02-03 to 2026-07-13 (1622 rows)
- Purge gap: 14 rows
- Mean backtest metrics: accuracy 0.5638, balanced accuracy 0.4081, macro F1 0.3733
- Final holdout metrics: accuracy 1.0000, balanced accuracy unavailable, macro F1 1.0000

Rolling-origin folds:

- Fold 1: train through 2024-04-09; test 2024-04-24 to 2024-10-02; balanced accuracy 0.5610; macro F1 0.5160
- Fold 2: train through 2024-09-18; test 2024-10-03 to 2025-03-13; balanced accuracy 0.3098; macro F1 0.3091
- Fold 3: train through 2025-02-27; test 2025-03-14 to 2025-08-22; balanced accuracy 0.3536; macro F1 0.2947

## EUR/RWF

### 7-day horizon

- Selected model: `random_forest`
- Final training window: 2022-02-03 to 2025-08-21 (1296 rows)
- Untouched holdout: 2025-08-29 to 2026-07-20 (326 rows)
- Production refit: 2022-02-03 to 2026-07-20 (1629 rows)
- Purge gap: 7 rows
- Mean backtest metrics: accuracy 0.4397, balanced accuracy 0.3743, macro F1 0.2960
- Final holdout metrics: accuracy 0.5184, balanced accuracy 0.3525, macro F1 0.2833

Rolling-origin folds:

- Fold 1: train through 2024-04-19; test 2024-04-27 to 2024-10-06; balanced accuracy 0.3333; macro F1 0.1942
- Fold 2: train through 2024-09-29; test 2024-10-07 to 2025-03-18; balanced accuracy 0.4083; macro F1 0.4075
- Fold 3: train through 2025-03-11; test 2025-03-19 to 2025-08-28; balanced accuracy 0.3812; macro F1 0.2863

### 14-day horizon

- Selected model: `logistic_regression`
- Final training window: 2022-02-03 to 2025-08-08 (1283 rows)
- Untouched holdout: 2025-08-23 to 2026-07-13 (325 rows)
- Production refit: 2022-02-03 to 2026-07-13 (1622 rows)
- Purge gap: 14 rows
- Mean backtest metrics: accuracy 0.3580, balanced accuracy 0.3532, macro F1 0.2717
- Final holdout metrics: accuracy 0.6154, balanced accuracy 0.3526, macro F1 0.3201

Rolling-origin folds:

- Fold 1: train through 2024-04-09; test 2024-04-24 to 2024-10-02; balanced accuracy 0.2962; macro F1 0.2444
- Fold 2: train through 2024-09-18; test 2024-10-03 to 2025-03-13; balanced accuracy 0.3333; macro F1 0.1398
- Fold 3: train through 2025-02-27; test 2025-03-14 to 2025-08-22; balanced accuracy 0.4302; macro F1 0.4309

## KES/RWF

### 7-day horizon

- Selected model: `random_forest`
- Final training window: 2022-02-03 to 2025-08-21 (1296 rows)
- Untouched holdout: 2025-08-29 to 2026-07-20 (326 rows)
- Production refit: 2022-02-03 to 2026-07-20 (1629 rows)
- Purge gap: 7 rows
- Mean backtest metrics: accuracy 0.3211, balanced accuracy 0.3746, macro F1 0.2386
- Final holdout metrics: accuracy 0.4479, balanced accuracy 0.4188, macro F1 0.3340

Rolling-origin folds:

- Fold 1: train through 2024-04-19; test 2024-04-27 to 2024-10-06; balanced accuracy 0.4252; macro F1 0.3262
- Fold 2: train through 2024-09-29; test 2024-10-07 to 2025-03-18; balanced accuracy 0.3243; macro F1 0.2043
- Fold 3: train through 2025-03-11; test 2025-03-19 to 2025-08-28; balanced accuracy 0.3742; macro F1 0.1852

### 14-day horizon

- Selected model: `logistic_regression`
- Final training window: 2022-02-03 to 2025-08-08 (1283 rows)
- Untouched holdout: 2025-08-23 to 2026-07-13 (325 rows)
- Production refit: 2022-02-03 to 2026-07-13 (1622 rows)
- Purge gap: 14 rows
- Mean backtest metrics: accuracy 0.4506, balanced accuracy 0.3756, macro F1 0.2389
- Final holdout metrics: accuracy 0.4246, balanced accuracy 0.3333, macro F1 0.1987

Rolling-origin folds:

- Fold 1: train through 2024-04-09; test 2024-04-24 to 2024-10-02; balanced accuracy 0.4630; macro F1 0.2422
- Fold 2: train through 2024-09-18; test 2024-10-03 to 2025-03-13; balanced accuracy 0.3333; macro F1 0.1991
- Fold 3: train through 2025-02-27; test 2025-03-14 to 2025-08-22; balanced accuracy 0.3304; macro F1 0.2755
