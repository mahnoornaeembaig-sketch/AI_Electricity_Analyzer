import os
import csv
import json
import re
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.getenv("API_KEY"))
MODEL_ID = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")

LEVEL1_PROMPT = """
You are a utility bill extraction agent. Extract non-identifying billing details from this bill image.
Return ONLY a valid JSON object matching this exact schema:
{
  "provider": "KE | LESCO | IESCO",
  "tariff": "string",
  "sanctioned_load_kw": number,
  "bill_month": "YYYY-MM",
  "reading_date": "YYYY-MM-DD",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD",
  "previous_reading": number,
  "current_reading": number,
  "units_consumed": number,
  "charges": [{"label": "string", "type": "energy|fixed|fpa|quarterly_adjustment|surcharge|meter_rent|subsidy|other", "amount": number}],
  "total_charges": number,
  "taxes": [{"label": "string", "type": "gst|electricity_duty|income_tax|municipal_tax|other_tax", "amount": number}],
  "total_taxes": number,
  "current_bill": number,
  "arrears": number,
  "payable_within_due_date": number,
  "payable_after_due_date": number
}
Rules:
- Numeric fields MUST be numbers, not strings. Use null for missing values. Subsidies are negative.
- NEVER add or combine lines. Output exactly one charge/tax entry per printed line, even if two lines have the same type.
- Extract the exact text printed on the bill into the "label" field for every charge and tax.
- If several amounts are printed for after the due date, return the largest available amount for "payable_after_due_date".
- Output pure JSON only.
"""

LEVEL2_PROMPT = """
Answer the following customer question about this electricity bill in plain English.
Here is the JSON data previously extracted from this bill for your reference:
{extracted_json}

Question: {question_text}

Rules:
- Base your answer ONLY on the provided bill and data.
- If a calculation is required, explain it briefly.
- Keep answers concise and direct. Exclude personal identifiers.
"""

def post_process_json(raw_text):
    text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        for c in data.get("charges", []):
            if "label" in c:
                del c["label"]
        for t in data.get("taxes", []):
            lbl = t.get("label", "").lower()
            if "sales" in lbl or "gst" in lbl:
                t["type"] = "gst"
            elif "duty" in lbl or "ed" in lbl:
                t["type"] = "electricity_duty"
            elif "muct" in lbl or "kmc" in lbl or "municipal" in lbl:
                t["type"] = "municipal_tax"
            if "label" in t:
                del t["label"]
        return json.dumps(data)
    except Exception:
        return text

def process_image(image_path, prompt, mime_type="application/json"):
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    
    # Auto-retry loop to handle API rate limits smoothly
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime), prompt],
                config=types.GenerateContentConfig(response_mime_type=mime_type)
            )
            return response.text.strip()
        except Exception as e:
            print(f" (API busy, pausing 10s to retry...) ", end="", flush=True)
            time.sleep(10)
            
    return "Error generating answer."

if __name__ == "__main__":
    os.makedirs("output", exist_ok=True)
    bill_dir = "test/bills"
    level1_input = "test/csv/level1.csv"
    level2_input = "test/csv/level2.csv"
    
    print("--- Starting Level 1: Extraction ---")
    level1_results = {}
    
    with open(level1_input, "r", encoding="utf-8") as fin, \
         open("output/level1.csv", "w", newline="", encoding="utf-8") as fout:
         
        reader = csv.reader(fin)
        writer = csv.writer(fout, quoting=csv.QUOTE_MINIMAL)
        header = next(reader)
        writer.writerow(header)
        
        for row in reader:
            if not row: continue
            bill_id = row[0]
            img_path = os.path.join(bill_dir, f"{bill_id}.png")
            if not os.path.exists(img_path):
                img_path = os.path.join(bill_dir, f"{bill_id}.jpg")
                
            print(f"Processing {bill_id}...")
            
            raw_json = process_image(img_path, LEVEL1_PROMPT, "application/json")
            final_json = post_process_json(raw_json)
            level1_results[bill_id] = final_json
            writer.writerow([bill_id, final_json])
            
            time.sleep(6) # Increased baseline wait to 6 seconds

    print("\n--- Starting Level 2: Q&A ---")
    if os.path.exists(level2_input):
        with open(level2_input, "r", encoding="utf-8") as fin, \
             open("output/level2.csv", "w", newline="", encoding="utf-8") as fout:
             
            reader = csv.reader(fin)
            writer = csv.writer(fout, quoting=csv.QUOTE_MINIMAL)
            header = next(reader)
            writer.writerow(header)
            
            for row in reader:
                if not row: continue
                bill_id, question_id, question, _ = row
                img_path = os.path.join(bill_dir, f"{bill_id}.png")
                if not os.path.exists(img_path):
                    img_path = os.path.join(bill_dir, f"{bill_id}.jpg")
                
                print(f"Answering {bill_id} - {question_id}...", end="")
                prompt = LEVEL2_PROMPT.format(extracted_json=level1_results.get(bill_id, "{}"), question_text=question)
                
                answer = process_image(img_path, prompt, "text/plain")
                writer.writerow([bill_id, question_id, question, answer])
                print(" Done.")
                
                time.sleep(6) # Increased baseline wait to 6 seconds
                    
    print("\nAll done! Check the 'output' folder for your final CSV files.")