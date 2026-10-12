# Utility Bill Decoder

Reads electricity bills (K-Electric, LESCO, IESCO) from images, extracts structured billing details as JSON (Level 1), and answers 12 customer questions per bill in plain English (Level 2).

**Runtime:** Python 3.12 (3.11 or later works)

---

## How it works

### Level 1: Extraction

- Each bill image (`.png` / `.jpg`) is sent to the Gemini vision model with a prompt containing the target JSON schema and the extraction rules.
- The output is parsed and validated as JSON, with every required field present (`null` when unreadable or covered).
- Each charge and tax line is kept as a separate entry, as printed.
- The JSON is written on one line into `output/level1.csv` using Python's `csv` module.

### Level 2: Question answering

- For each bill, the 12 questions from `level2.csv` are answered using the extracted JSON and the bill image.
- Answers are grounded in the bill, written in English, and label any estimates.
- Calculations such as comparisons and explanations are handled by the model, based on the provided bill and extracted data.
- Results are written into `output/level2.csv`.

### Reliability

- Automatic retries with backoff handle the free-tier limits (15 requests/min, 500 requests/day).
- A failure on one bill or question is logged and does not stop the run.
- If a call still fails after several retries, a default error message or empty object is written, so no cell is left empty.

---

## Setup

**1. Create and activate a virtual environment**

```bash
python -m venv venv

venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS / Linux
```

**2. Install pinned dependencies**

```bash
pip install -r requirements.txt
```

**3. Create your `.env` from the template and add your Gemini API key**

```bash
copy .env.example .env         # Windows
cp .env.example .env           # macOS / Linux
```

### Environment variables

| Variable | Purpose | Value in `.env.example` |
|---|---|---|
| `MODEL_PROVIDER` | Model provider | `google` |
| `MODEL_NAME` | Model ID | `gemini-3.5-flash-lite` |
| `API_KEY` | Gemini API key | `your-api-key-here` |

---

## Running

From the `source/` folder:

```bash
python run.py
```

By default it reads bills from `test/bills` and the CSV templates from `test/csv`, and writes `level1.csv` and `level2.csv` to `output`.

A full run makes about 130 model calls (10 for Level 1, 120 for Level 2), so expect roughly 10 minutes on the free tier because of the rate-limit sleep intervals.

---

## AI usage

| Category | Details |
|---|---|
| **Models called by the solution** | Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`), for Level 1 extraction and Level 2 answers |
| **APIs and services** | Google AI Studio (Gemini API), via the `google-genai` Python SDK |
| **Local OCR / other ML libraries** | none |
| **Prohibited services** | none used (no invoice/receipt extraction agents, Azure prebuilt-invoice, Textract AnalyzeExpense, or Mindee) |
| **AI tools used to help write the code** | Gemini personal AI collaborator (code structuring, rate-limit handling, README drafting) |

---

## Limitations

- Very blurry or heavily tilted photos may reduce extraction accuracy.
- Values are extracted as printed and are not recalculated or corrected outside the model's standard comprehension.