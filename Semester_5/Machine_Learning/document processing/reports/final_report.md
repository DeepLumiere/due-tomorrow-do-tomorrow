# Machine Learning Innovative Assignment: Final Project Report
## End-to-End Invoice & Receipt Processing Pipeline with Trained Field Reliability Verification

---

### Executive Summary
Automated document intelligence systems that ingest receipt and invoice images using pre-trained vision-language or OCR-LLM architectures (e.g. Docling + Gemma3n-E2B) face a critical operational limitation: **small generative models frequently hallucinate values, transpose digits, or drop modifiers without providing well-calibrated confidence scores**. 

Rather than presenting an unverified, black-box LLM pipeline, this project develops a complete, justified, reproducible, and usable Machine Learning solution conforming to all 12 stages of the course guidelines. While layout parsing (Docling RapidOCR) and zero-shot schema extraction (Gemma3n-E2B via Ollama) serve as the pre-trained ingestion backbone, the core machine learning work is a **Supervised Field Verifier Classifier**. This model inspects extracted fields, scores their probability of correctness, and autonomously routes low-confidence fields to a human-in-the-loop review queue before inserting validated records into a partitioned, immutable Parquet datastore.

On the official CORD benchmark (973 deduplicated receipts, 10,260 extraction fields), our tuned and calibrated tree ensemble achieves a Test PR-AUC of **0.9212** (95% CI: [0.8385, 1.0]) and Test ROC-AUC of **0.9782**, substantially outperforming both majority and heuristic rule baselines, while enabling **> 96% auto-acceptance coverage at 99.9% accuracy**.

---

### Stage 1: Problem Definition & Use Case
- **Real-World Problem:** Small and medium enterprises (SMEs), accountants, and financial auditors receive thousands of paper receipts and digital invoices weekly. Manual data entry is slow and error-prone, yet unverified OCR/LLM automation is hazardous because undetected extraction errors lead to severe accounting and tax discrepancies.
- **Stakeholders & Users:** Business owners, accounting clerks, inventory managers, and compliance auditors.
- **Objectives:**
  1. Ingest scanned receipt/invoice images and convert them into strongly typed, relational Parquet tables (`documents`, `line_items`, `fields`).
  2. Train an ML verifier to estimate $P(\text{field is correct})$.
  3. Flag suspicious or hallucinated fields for manual review in a Gradio UI, minimizing human verification effort while maintaining near-perfect data accuracy.
- **Inputs & Outputs:**
  - *Input:* Receipt image (JPG/PNG) or digital PDF.
  - *Output:* Normalized Pydantic JSON record, persistent columnar Parquet files queryable via DuckDB, per-field confidence scores, and review queue flags.
- **Constraints:** Fully local execution (no proprietary third-party cloud APIs); resource-constrained execution on standard hardware; strict auditability and data leakage prevention.

---

### Stage 2: Data Acquisition & Understanding
- **Dataset Source:** Consolidated Receipt Dataset (`naver-clova-ix/cord-v2`) hosted on the Hugging Face Hub, acquired via `datasets.load_dataset`.
- **License & Ownership:** Creative Commons Attribution 4.0 International (CC-BY-4.0). Receipts are photographic captures of Indonesian retail, restaurant, and service stores.
- **Size & Splits:** 1,000 original annotated receipts (800 train / 100 validation / 100 test).
- **Features & Annotations:** Raw RGB image, bounding box OCR coordinates, and nested JSON ground truth (`gt_parse`) containing line items (`menu`: name, count, unit price, total price, sub-modifiers), `sub_total`, and `total`.
- **Domain Limitations & Honesty:**
  CORD comprises photographic Indonesian store receipts rather than multi-page European B2B invoices. Consequently, official ground truth exists for items, subtotals, taxes, and totals, but **not** for extended fields such as vendor tax IDs, invoice numbers, or payment terms. Our schema extracts extended fields when available, but marks them as unverified (`verified = null`) to preserve evaluation integrity.

---

### Stage 3: Data Preparation
Implemented in [`src/data/cord_clean.py`](file:///R:/DeepWorks/DeepResearch/mrilabs/ml_assignment/src/data/cord_clean.py) and audited in [`reports/data_audit.json`](file:///R:/DeepWorks/DeepResearch/mrilabs/ml_assignment/reports/data_audit.json).
- **Format Standardization:**
  - The nested `menu` structure in CORD inconsistently varies between single dictionary mappings and lists of dictionaries. We normalized all instances into a uniform list of structured dictionaries.
  - Sub-modifiers (`sub_nm`, `sub`) were flattened into string modifier arrays.
  - `void_menu` items (canceled orders) were isolated and flagged with `is_void = True` so they do not contaminate active receipt totals.
- **Perceptual Deduplication & Cross-Split Leakage Prevention:**
  - Exact duplicates were identified via SHA-256 byte hashing (2 pairs found).
  - Perceptual near-duplicates were detected using perceptual hashing (`imagehash.phash`, Hamming distance $\le 2$, 78 near-duplicate pairs found).
  - **Crucial Leakage Control:** 28 cross-split duplicate pairs were discovered between the training split and the validation/test splits. To strictly guarantee that the test split represents unseen documents, **27 duplicate receipts were permanently removed from the training split**, resulting in a final cleaned dataset of 973 receipts (773 train / 100 val / 100 test).
- **Record Counts:**
  - Raw inputs: 1,000 documents.
  - Post-cleaning: 973 documents; 11,894 long-format ground truth field rows.

---

### Stage 4: Data Preprocessing
- **Amount & Currency Normalization:**
  Indonesian financial formatting employs periods as thousand separators and commas as decimals (e.g. `16.500` represents 16,500 IDR, and `1.500,50` represents 1,500.50). In addition, Indonesian receipts frequently use trailing shorthand zero-cent markers (e.g. `10.000,-` or `10.000.-`), accounting negative parentheses `(16.500)`, and currency prefixes (`Rp`, `IDR`).
  Our custom parsing engine in [`src/pipeline/normalize.py`](file:///R:/DeepWorks/DeepResearch/mrilabs/ml_assignment/src/pipeline/normalize.py) resolves ambiguous separators, strips non-numeric artifacts, and emits exact `Decimal` types.
- **Text Normalization:** Unicode NFKC normalization, whitespace stripping, and multiple-space collapse via `clean_text`.
- **Missing Values:** Missing fields in receipts (e.g., discount, tax, service charge) represent physical absence in the source transaction, not random corruption. Therefore, they are retained as explicit `null` values rather than synthetically imputed.
- **Outlier Analysis:**
  Outlier bounds were computed using the Interquartile Range ($Q_1 - 1.5\text{IQR}$, $Q_3 + 1.5\text{IQR}$) and $99.5^{\text{th}}$ percentile thresholds. Document grand totals exhibited a median of 45,500 Rp and a $p99$ of 1,565,938 Rp. Price outliers were reviewed and retained as valid high-value commercial catering transactions.

---

### Stage 5: Data Balancing
- **Imbalance Measurement:**
  Across 10,260 extracted fields, only 288 fields (2.81%) represent extraction errors or hallucinations. This presents an **extreme class imbalance** (positive error class $\approx 2.8\%$).
- **Methodology & Leakage Prevention:**
  - Evaluating accuracy alone is mathematically deceptive (a trivial model predicting "always correct" achieves 97.2% accuracy while failing 100% of its verification mission).
  - Resampling (SMOTE) and cost-sensitive class weights (`class_weight='balanced'`) were evaluated strictly inside cross-validation folds using `imblearn.pipeline.Pipeline`. Validation folds were never resampled.
- **Decision & Validation:**
  Cost-sensitive inverse-frequency class weighting in tree ensembles demonstrated superior PR-AUC and calibration compared to SMOTE, avoiding synthetic artifact generation on mixed one-hot and continuous features.

---

### Stage 6: Exploratory Data Analysis (EDA)
EDA was performed analytically via [`src/data/run_eda.py`](file:///R:/DeepWorks/DeepResearch/mrilabs/ml_assignment/src/data/run_eda.py) with visual artifacts saved to `reports/eda/`:
1. **Univariate Analysis (`dist_line_items.png`):** Line items per receipt follow a right-skewed distribution with a mean of 2.58 items, median of 2.0, and $p95$ of 7.0 items.
2. **Amount Distribution (`dist_grand_total_log.png`):** Grand totals span several orders of magnitude ($10^3$ to $10^6$ Rp), confirming the requirement for relative error metrics rather than absolute difference thresholds.
3. **Field Frequencies (`gt_field_frequencies.png`):** Line item descriptions and line totals dominate the dataset (> 50% of all fields), while discount and service charges occur in < 15% of transactions.
4. **Missing Rates (`missing_rates.png`):** Subtotal is absent in 33.9% of receipts, tax in 56.5%, and discount in 92.8%, directly influencing the design of adaptive arithmetic consistency checks.

---

### Stage 7: Feature Engineering & Selection
Implemented in [`src/verifier/features.py`](file:///R:/DeepWorks/DeepResearch/mrilabs/ml_assignment/src/verifier/features.py). To ensure zero data leakage, **no feature ever accesses ground truth**.
1. **Source Grounding Features:**
   - `exact_in_text`: Binary indicator whether the extracted string appears verbatim in the Docling OCR text.
   - `fuzzy_ratio`: RapidFuzz partial ratio score measuring character-level overlap against source text.
   - `digits_in_text`: Binary check whether numerical digits exist in source text after removing formatting.
2. **OCR Engine Confidence:**
   - `mean_ocr_conf`, `min_ocr_conf`: Average and minimum RapidOCR token confidences for bounding boxes corresponding to the extracted value.
   - `has_ocr_conf`: Missingness flag column.
3. **Cross-Field Arithmetic Consistency:**
   - `items_diff`: Relative difference between $\sum \text{line\_total}$ and extracted `subtotal`.
   - `grand_diff`: Relative discrepancy in $\text{total} - (\text{subtotal} + \text{tax} + \text{service} - \text{discount})$.
   - `item_mul_diff`: Multiplicative check $|\text{qty} \times \text{unit\_price} - \text{line\_total}|$.
4. **Structural & Contextual Features:**
   - `digit_frac`, `n_chars`, `looks_like_amount`, `value_is_round` (identifying IDR multiples of 1,000).
   - `relative_position`: Vertical/sequential offset of the token in the document (header vs body vs footer).

---

### Stage 8: Baseline Models
Two non-trivial reference points were established:
- **Baseline B0 (Majority Class Predictor):**
  Predicts every field is correct ($y=0$).
  - *Accuracy:* 97.19%
  - *Error PR-AUC:* **0.0281**
  - *Error Recall:* **0.0%**
  - *Significance:* Demonstrates why raw accuracy is useless for safety-critical verification.
- **Baseline B1 (Heuristic Rule Baseline):**
  Predicts error ($y=1$) if the field is not grounded in text or if document-level arithmetic checks fail.
  - *Error PR-AUC:* **0.0417**
  - *Error Recall:* 97.31%
  - *Error Precision:* 4.21%
  - *Significance:* High recall but catastrophic false alarm rate (over-flagging 96% of correct fields), demonstrating the absolute necessity of supervised machine learning.

---

### Stage 9: Machine Learning Modelling
We evaluated three supervised models using 5-fold `StratifiedGroupKFold` grouped by `doc_id`:
1. **Model M1: Regularized Logistic Regression (L2):**
   - *Rationale:* Interpretable linear decision boundary; standard baseline.
   - *5-Fold Group CV PR-AUC:* **0.8254** ($\pm 0.0999$)
2. **Model M2: Random Forest Classifier:**
   - *Rationale:* Non-linear decision trees robust to feature scaling and collinearity.
   - *5-Fold Group CV PR-AUC:* **0.9316** ($\pm 0.0614$)
3. **Model M3: Histogram-Based Gradient Boosting (`HistGradientBoostingClassifier`):**
   - *Rationale:* State-of-the-art tabular gradient boosting natively binning continuous features, handling missing values, and capturing complex interactions between arithmetic discrepancy flags and OCR token confidences.
   - *5-Fold Group CV PR-AUC:* **0.9407** ($\pm 0.0419$) (Superior performance across all folds).

---

### Stage 10: Hyperparameter Tuning & Probability Calibration
Implemented in [`src/verifier/train.py`](file:///R:/DeepWorks/DeepResearch/mrilabs/ml_assignment/src/verifier/train.py):
- **Tuning Strategy:** `RandomizedSearchCV` (20 iterations) nested inside `StratifiedGroupKFold`, optimizing Average Precision (PR-AUC) on the minority error class.
  - Best parameters: `min_samples_leaf=20`, `max_leaf_nodes=31`, `learning_rate=0.20`, `l2_regularization=1.0`.
  - Tuned 5-Fold Group CV PR-AUC increased to **0.9446**.
- **Probability Calibration:**
  Raw boosting margins do not yield reliable probabilities. We calibrated the tuned ensemble using `CalibratedClassifierCV(method='sigmoid')` fitted via cross-validation folds.
  - Resulting Brier Score: **0.0045** (near-perfect probability calibration confirmed via `reports/calibration_curve.png`).

---

### Stage 11: Validation & Rigorous Evaluation
Evaluated strictly **once** on the 100-document test split (998 fields):
- **Headline Performance Metrics:**
  - **Test PR-AUC:** **0.9212** (Receipt-level 1,000-resample bootstrap 95% CI: `[0.8385, 1.0]`)
  - **Test ROC-AUC:** **0.9782** (95% CI: `[0.9503, 1.0]`)
  - **Balanced Accuracy:** **0.9577**
  - **Error Recall:** **92.86%** (13 of 14 errors caught; only 1 false negative).
  - **Brier Score:** **0.0045** (95% CI: `[0.0012, 0.0071]`).
- **Risk-Coverage Curve Analysis (`reports/risk_coverage_curve.png`):**
  - Ranking fields by verifier confidence allows **85% of fields to be auto-accepted with an error rate of 0.12% (99.88% accuracy)**.
  - At **96% coverage**, accuracy on the accepted set remains **99.90%**, compared to the unfiltered raw accuracy of 98.60%.
  - This translates to an **85–95% reduction in manual verification labor** while guaranteeing higher overall data quality.

---

### Stage 12: Practical Impact, System Architecture & Limitations
- **Architectural Flow:**
  `Image/PDF Ingest` $\rightarrow$ `Docling RapidOCR (cached)` $\rightarrow$ `Ollama Gemma3n:e2b JSON Schema filling` $\rightarrow$ `Normalization & Arithmetic Checks` $\rightarrow$ `Field Verifier Scoring` $\rightarrow$ `Parquet Store (DuckDB)` $\rightarrow$ `Gradio UI Review Queue`.
- **Stakeholder Benefit:**
  Users inspect only fields flagged with $P(\text{correct}) < 0.85$ in the Gradio UI. Corrected values are saved back to Parquet with `user_corrected=True` and `status="corrected"`, creating an active-learning audit loop.
- **Identified Limitations:**
  1. *Receipts vs Invoices:* CORD represents single-page retail receipts; multi-page enterprise purchase orders with tabular tax matrices require multi-page document layout expansion.
  2. *Recall of Omitted Items:* The verifier scores predicted fields; if the upstream OCR fails to detect an entire physical line item on a torn receipt, the verifier cannot flag an absent row.
- **Future Improvements:** Integrate Hungarian bipartite bounding box coordinates directly into attention layers and fine-tune small vision-language models on verified human corrections.
