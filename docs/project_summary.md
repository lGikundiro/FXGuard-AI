# FXGuard AI Project Summary

FXGuard AI is a web-based exchange-rate risk forecasting, classification, and decision-support system for Rwanda-based importers. It classifies short-term depreciation risk for USD/RWF, EUR/RWF, and KES/RWF into Low, Medium, or High categories using engineered features from official BNR exchange-rate data.

The MVP supports:

1. Three foreign currencies against RWF: USD, EUR, and KES
2. Payment assessment in the selected foreign currency
3. Risk results
4. Decision support
5. Usability feedback collection

The project uses public BNR data and does not require private bank or business records for model training. Its USD, EUR, and KES histories come exclusively from the official BNR Excel exports stored locally in `data/raw/`.
