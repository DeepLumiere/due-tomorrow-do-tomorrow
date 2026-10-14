# Model Card: Invoice & Receipt Field Verifier (v1.0)

## 1. Model Details
- **Model Name:** Field Verifier (Invoice & Receipt Reliability Classifier)
- **Model Architecture:** HistGradientBoostingClassifier (Ensemble of Decision Trees with Histogram-based Binning) + Sigmoid Probability Calibration
- **Version:** 1.0.0
- **Trained By:** ML Assignment Team
- **Framework:** scikit-learn 1.7.0, imbalanced-learn 0.14.0
- **Model Storage:** `models/verifier_v1.joblib`

## 2. Intended Use
- **Primary Use Case:** Automated post-OCR/LLM verification for financial receipts and invoices. For each extracted field, predicts `P(field is correct)`. Fields falling below a calibrated confidence threshold (default 85%) are routed to an interactive human-in-the-loop review queue.
- **Intended Users:** Small businesses, accountants, invoice processing systems requiring audit trails and risk-controlled automation.
- **Out-of-Scope Uses:** Autonomous payments or money transfers without verification; non-tabular freeform prose verification.

## 3. Training Data & Leakage Control
- **Source Dataset:** Consolidated Receipt Dataset (`naver-clova-ix/cord-v2`), Indonesian photographed receipts (train: 773, val: 100, test: 100 receipts after deduplication).
- **Target Variable:** Binary `is_error` (1 if extracted field is incorrect, missing, or hallucinated; 0 if correct).
- **Leakage Prevention:**
  - Receipts strictly partitioned using `StratifiedGroupKFold(n_splits=5, groups=doc_id)`. All fields belonging to any single receipt remain in the same fold.
  - Perceptual hash and SHA-256 cross-split duplicates dropped from training.
  - Verification features NEVER receive ground truth values.

## 4. Feature Groups
1. **Identity:** `field_name` (one-hot), `is_line_item` (binary).
2. **Grounding in Source OCR:** `exact_in_text` (binary), `n_occurrences` (int), `fuzzy_ratio` (0.0–1.0 via RapidFuzz), `digits_in_text` (binary).
3. **OCR Engine Signals:** `mean_ocr_conf`, `min_ocr_conf`, `has_ocr_conf` (RapidOCR confidence token scores).
4. **Cross-Field Arithmetic Consistency:**
   - Line items sum vs extracted subtotal (`items_consistent`, `items_diff`).
   - Grand total equation: `total == subtotal + tax + service - discount` (`grand_consistent`, `grand_diff`).
   - Quantity multiplier consistency: `qty * unit_price == line_total` (`item_mul_consistent`, `item_mul_diff`).
5. **Formatting & Context:** Character length, digit fraction, regex amount validity, round number indicator (multiples of 1000 IDR), total document length, relative text position.

## 5. Quantitative Evaluation
- **Baseline Models:**
  - Majority Baseline (B0): PR-AUC = 0.028 (accuracy paradox demonstration).
  - Rule-Based Baseline (B1): Grounding & arithmetic heuristic check.
- **Model Comparison (5-Fold Grouped CV PR-AUC):**
  - Logistic Regression (L2, scaled): ~0.8254
  - Random Forest: ~0.9316
  - HistGradientBoosting: ~0.9407 (Best)
- **Tuned & Calibrated HGB on Test Split:**
  - Test PR-AUC: > 0.90 (with 95% receipt-level cluster bootstrap confidence intervals)
  - Test ROC-AUC: > 0.95
  - Reliability Diagram Brier Score: < 0.03
- **Risk-Coverage Curve:** Demonstrates that auto-accepting high-confidence fields allows > 85% automation coverage while maintaining > 98.5% accuracy on accepted records.

## 6. Limitations & Ethical Considerations
- **Language & Geography:** Trained on Indonesian retail/restaurant receipts. Extended invoice fields (tax ID, vendor address, Western IBAN) require local adaptation.
- **Recall Misses:** Detects errors in predicted fields; does not detect entire line items omitted by the upstream OCR/LLM.
