# FXGuard AI Flexible-Horizon Model Evaluation

Generated: 2026-08-02T10:32:37+00:00

Each currency has one horizon-aware classifier. The requested number of calendar days (1–100) is a model feature, and training contains outcomes for every integer horizon.

Evaluation splits on observation dates. A training row is removed whenever its future outcome date reaches the test period, with up to a 100-day boundary purge. Risk-label thresholds are learned independently for each horizon from training dates only.

## USD/RWF

- Selected model: `logistic_regression`
- Reliability status: `experimental_not_trustworthy`
- Supervised rows: 105240
- Mean rolling metrics: accuracy 0.6386, balanced accuracy 0.4472, macro F1 0.2801
- Holdout metrics: accuracy 1.0000, balanced accuracy unavailable, macro F1 1.0000

Holdout metrics by requested payment period:

- 1-14d: balanced accuracy unavailable; macro F1 1.0000; 2983 rows
- 15-30d: balanced accuracy unavailable; macro F1 1.0000; 3250 rows
- 31-60d: balanced accuracy unavailable; macro F1 1.0000; 5639 rows
- 61-100d: balanced accuracy unavailable; macro F1 1.0000; 6568 rows

## EUR/RWF

- Selected model: `xgboost`
- Reliability status: `experimental_not_trustworthy`
- Supervised rows: 105240
- Mean rolling metrics: accuracy 0.3084, balanced accuracy 0.2987, macro F1 0.1680
- Holdout metrics: accuracy 0.8164, balanced accuracy 0.3667, macro F1 0.3646

Holdout metrics by requested payment period:

- 1-14d: balanced accuracy 0.3582; macro F1 0.3366; 2983 rows
- 15-30d: balanced accuracy 0.3596; macro F1 0.3387; 3250 rows
- 31-60d: balanced accuracy 0.5531; macro F1 0.5412; 5639 rows
- 61-100d: balanced accuracy 0.4983; macro F1 0.4912; 6568 rows

## KES/RWF

- Selected model: `random_forest`
- Reliability status: `experimental_not_trustworthy`
- Supervised rows: 105240
- Mean rolling metrics: accuracy 0.4982, balanced accuracy 0.4016, macro F1 0.2470
- Holdout metrics: accuracy 0.2481, balanced accuracy 0.3329, macro F1 0.1326

Holdout metrics by requested payment period:

- 1-14d: balanced accuracy 0.3333; macro F1 0.1850; 2983 rows
- 15-30d: balanced accuracy 0.3315; macro F1 0.1660; 3250 rows
- 31-60d: balanced accuracy 0.3333; macro F1 0.1453; 5639 rows
- 61-100d: balanced accuracy 0.5000; macro F1 0.1063; 6568 rows
