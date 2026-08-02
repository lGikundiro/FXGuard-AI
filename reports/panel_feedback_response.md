# FXGuard AI: Response to Defense Panel Feedback

Updated: 2 August 2026

## Revised research position

FXGuard AI does **not** solve exchange-rate depreciation and does not remove, hedge, or insure an importer's foreign-currency exposure. It is an experimental decision-support prototype that classifies short-term depreciation pressure and translates the result into a planning estimate. The system's contribution is therefore risk visibility and payment-planning support, not elimination of the underlying financial risk.

### Aligned problem statement

Rwanda-based importers that earn RWF and have foreign-currency supplier obligations face uncertain RWF payment costs when exchange rates move before settlement. Existing official rates show current and historical prices, but they do not provide a validated importer-specific short-term risk classification or payment-cost scenario. This project investigates whether a transparent classifier built from official BNR data can add useful decision support. It does not assume that all importers are unable to read exchange-rate data.

### Aligned objective

Design and evaluate a prototype that accepts the user's planned invoice payment date, classifies foreign-currency/RWF depreciation pressure over the resulting 1–100-day period as Low, Medium, or High, communicates uncertainty and data freshness, and estimates the RWF cost and a planning buffer for a user-supplied invoice amount.

## Actions taken

| Panel concern | Change made | Current conclusion |
|---|---|---|
| Problem–solution mismatch | Reframed the system as risk classification and payment-planning support; removed any claim that it solves depreciation or hedges exposure. | Scope now matches the delivered system. |
| 51.7% accuracy / reliability | Added forward-only backtesting, untouched holdout evaluation, training-only label thresholds, a most-frequent baseline, balanced accuracy, macro F1, and a pre-declared reliability gate. | No current model passes the gate; all are explicitly experimental. |
| Unsupported claim about importers' interpretation | Reviewed Rwanda-specific evidence and removed the universal "cannot interpret" claim. The revised need is exposure plus the potential value of tested decision support. | Importer interpretation is now a user-research question, not an asserted fact. |
| Missing macro drivers | Defined a leakage-safe macro-data plan using publication dates and lagged joins. | Not yet included in production because adding low-frequency values without publication-lag controls would create false precision or leakage. |
| Weekend forward-fill | Model training now uses actual BNR postings only. The forward-filled daily calendar remains only for display. Every 1–100-day outcome uses the first official posting on or after its target date. | Artificial weekend zero returns no longer enter model training. |

## Reliability decision

The project now declares a model provisionally acceptable only if all three conditions are met across rolling folds:

1. Mean balanced accuracy is at least 0.55.
2. Mean macro F1 is at least 0.45.
3. Mean balanced accuracy exceeds the most-frequent baseline by at least 0.05.

These are transparent, project-defined research gates, not universal financial-industry standards. They prevent the project from describing a model as trustworthy merely because it is slightly above chance or has high accuracy during a one-class period.

The rationale is deliberately conservative but simple to defend: 0.55 balanced accuracy is 21.7 percentage points above the 0.333 equal-class reference; 0.45 Macro F1 prevents a model with one or two neglected classes from passing on balanced accuracy alone; and the 0.05 baseline margin requires a practically visible gain over the dataset's simplest rule. A future production threshold should additionally be set through importer loss analysis—for example, assigning a higher cost to missed High-risk periods—and prospective validation on newly collected dates.

| Pair | Supported period | Selected model | Accuracy | Balanced accuracy | Macro F1 | Gate |
|---|---:|---|---:|---:|---:|---|
| USD/RWF | 1–100 days | Logistic Regression | 0.6386 | 0.4472 | 0.2801 | Fail |
| EUR/RWF | 1–100 days | XGBoost | 0.3084 | 0.2987 | 0.1680 | Fail |
| KES/RWF | 1–100 days | Random Forest | 0.4982 | 0.4016 | 0.2470 | Fail |

All three flexible models remain below the reliability gate. The API and interface expose failed-gate predictions as experimental and describe the displayed value with an approximation sign as an uncalibrated model score. Detailed evaluation is also reported for 1–14, 15–30, 31–60, and 61–100-day bands so pooled performance cannot hide a weak range.

## Evidence for the actual problem

The strongest defensible evidence supports **foreign-exchange exposure**, not a blanket claim that importers cannot understand a rate table:

- Bai, Spray, and Miyauchi's Rwanda study uses customs and firm transaction data and reports that exchange-rate fluctuations significantly affect import prices, with estimated elasticities between 0.1 and 0.4. This supports the import-cost problem directly: [International Growth Centre, “Impacts of exchange rate fluctuations on imports and domestic economy in Rwanda”](https://www.theigc.org/publications/impacts-exchange-rate-fluctuations-imports-and-domestic-economy-rwanda).
- Rwanda's 2024 Integrated Business Enterprise Survey reports that 87% of the business landscape is informal and identifies advanced/specialized IT skills among managers' leading skills-gap concerns. Its finance tables also show uneven access to foreign-exchange and trade-finance instruments. This supports designing for small and resource-constrained firms, but it does **not** prove that importers cannot interpret exchange-rate data: [NISR Integrated Business Enterprise Survey 2024](https://statistics.gov.rw/statistical-publications/business-establishment-finance-trade/business-establishment-finance-trade/integrated-business-enterprise-survey-2024).
- BNR's 2022–2023 annual report records a diagnostic study of MSME financial literacy. This establishes that financial capability is a recognized policy concern, but it is not importer-specific evidence of inability to interpret exchange rates: [BNR Annual Report 2022–2023](https://www.bnr.rw/fileadmin/user_upload/Annual_Report_2022-23_Engl_Compressed.pdf).

### Claim the defense should use

> The literature establishes that exchange-rate movements affect Rwandan import prices and that many Rwandan firms operate with constrained financial and technical capacity. It does not directly establish that importers cannot interpret published exchange-rate data. FXGuard therefore treats the usefulness and comprehensibility of risk classification as an empirical user-testing question rather than an assumed fact.

To close this evidence gap, future user testing should recruit actual importers and measure: ability to interpret a BNR rate table without FXGuard; ability to identify cost direction and calculate RWF exposure; decision time; error rate; and improvement after using FXGuard. Until then, the report should say “may benefit from simplified decision support,” not “cannot interpret exchange-rate data.”

## Responsible macro-feature plan

Macroeconomic variables should be added as an ablation experiment, not assumed to improve forecasts across the 1–100-day range. IMF research notes that macro fundamentals can explain longer exchange-rate cycles better than short cycles, and some out-of-sample models with fundamentals do not beat a random walk at short horizons: [IMF, “Exchange-Rate Swings and Foreign Currency Intervention”](https://www.elibrary.imf.org/view/journals/001/2022/158/article-A001-en.xml) and [IMF, “Structural Factors Affecting Exchange Rate Volatility”](https://www.elibrary.imf.org/view/journals/001/2004/147/article-A001-en.xml).

Proposed variables and sources:

- Rwanda headline, imported-goods, energy, and transport inflation from monthly NISR CPI releases: [NISR CPI](https://statistics.gov.rw/data-sources/surveys/Consumer-Price-Index/consumer-price-index-cpi-2026).
- BNR policy rate and monetary-policy indicators from BNR publications.
- Monthly Brent/crude-oil and commodity prices from the World Bank Pink Sheet: [World Bank Commodity Markets](https://www.worldbank.org/en/research/commodity-markets).
- Trade balance/import bill at its official monthly or quarterly frequency where a stable source and publication calendar are available.

For every series, the dataset must retain both `reference_period` and `published_at`. A rate observation may receive only the latest macro value that had actually been published by that date. Values may be carried forward after publication, with `macro_age_days` included as a feature; they must never be backfilled into dates before publication. The macro model must then be compared with the rate-only baseline on identical rolling folds. It should be retained only if it improves out-of-sample results and remains stable across currencies and periods.

## Defense-ready conclusion

FXGuard AI now matches its claim to its implementation: it is an experimental risk-classification and payment-planning prototype, not a solution to currency depreciation. The revised evaluation is deliberately stricter than the original 51.7% accuracy result. It removes forward-filled weekend rows from training, prevents future label thresholds from entering earlier folds, compares against a simple baseline, and applies an explicit reliability gate. None of the current models passes that gate, so the correct conclusion is that the software prototype functions, but predictive reliability has not yet been demonstrated. The next model-development phase should test publication-lagged macro features and collect genuinely new outcomes; the next user-research phase should test importer comprehension rather than assume it.
