# Academic Integrity & AI Assistance Usage Log

Per Section 9 of the *Innovative Assignment Guidelines & Requirements*:
> "Students may use AI-assisted tools for brainstorming, coding support, debugging, documentation or learning where permitted by course policy. However, students remain responsible for understanding, verifying and being able to explain every part of their project... Maintain a record of major datasets, code sources, libraries and external resources used."

---

## 1. Primary Datasets Used
- **Name:** Consolidated Receipt Dataset (CORD-v2)
- **Source:** `naver-clova-ix/cord-v2` on Hugging Face Hub
- **License:** Creative Commons Attribution 4.0 International (CC-BY-4.0)
- **Citations:** Park, Seunghyun, et al. "CORD: A Consolidated Receipt Dataset for Post-OCR Parsing." NeurIPS 2019 Workshop on Document Intelligence.

## 2. Core Libraries & External Tools
- **Document OCR & Layout:** `docling` (IBM Research Document Converter) with `rapidocr` (ONNXRuntime PP-OCRv4 detection and recognition engines).
- **LLM Structured Extraction:** Ollama `0.22.1` serving local open weights `gemma3n:e2b` (Google Gemma 3n Effective 2B) using native JSON Schema validation (`format=InvoiceExtraction.model_json_schema()`).
- **Data Engineering & Storage:** `pyarrow` (schema-enforced immutable columnar Parquet part-files), `duckdb` (in-memory relational SQL query engine for analytical querying), `pydantic v2` (strongly typed domain validation).
- **Machine Learning & Verification:** `scikit-learn` (`HistGradientBoostingClassifier`, `RandomForestClassifier`, `LogisticRegression`, `StratifiedGroupKFold`, `CalibratedClassifierCV`, `RandomizedSearchCV`), `imbalanced-learn` (`SMOTE`, `Pipeline`), `rapidfuzz` (Levenshtein token sort ratio), `scipy` (`linear_sum_assignment` for bipartite Hungarian alignment).
- **User Interface & Visualization:** `gradio` (Interactive Web UI for live upload, review queue, DuckDB dataset explorer), `matplotlib` & `seaborn` (publication plots for PR-AUC, ROC-AUC, Reliability calibration, and Risk-Coverage curves).

## 3. Record of AI Assistance
| Stage | Purpose of AI Assistance | Verification Performed |
|---|---|---|
| Pipeline Architecture | Designing multi-stage flow connecting Docling, Ollama structured schema, and Parquet storage | Verified all data types, schemas, and file IO contracts against Pydantic v2 and PyArrow specifications. |
| Schema Design | Formulation of flat `InvoiceExtraction` and long-format `FieldResult` models | Verified schema compilation and tested serialization round-trip via pytest. |
| CORD Cleaning & Normalization | Writing regex heuristics for Indonesian thousand-dots, comma decimals, and trailing `,-` shorthand | Validated against 20+ automated unit tests covering edge cases (`16.500`, `1.500,50`, `10.000,-`, etc.). |
| Label Alignment | Implementing Hungarian bipartite matching with RapidFuzz for line items | Manually inspected matched item pairs and verified distance thresholds. |
| Model Training & Tuning | Scaffolding StratifiedGroupKFold, model exploration, and calibration | Verified that no data leakage occurs across receipt groups; verified bootstrap CI logic on test split. |
| UI Development | Creating 3-tab Gradio interface | Verified interactive event callbacks, DuckDB query execution, and Parquet export. |

All code, metrics, and experimental results presented in this project have been executed, tested, and validated locally on the assignment environment.
