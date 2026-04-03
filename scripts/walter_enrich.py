"""Enrich new walter.csv rows with entity extraction + sentiment via Ollama.

- ThreadPoolExecutor with 2 workers (1 per GPU)
- Generate API with deepseek-v2:16b (~20x faster than qwen3.5:9b thinking)
- 40/60 GPU split (GPU0 has display, gets less work)
- Incremental: only processes rows after last date in walter_openai.csv
- Batch flushing every 50 rows to avoid data loss on long runs
"""

import csv
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import requests

WALTER_CSV = os.getenv("WALTER_CSV")
WALTER_OPENAI_CSV = os.getenv("WALTER_OPENAI_CSV")

GPU0_PORT = 11435  # GPU 0 (display GPU, less work)
GPU1_PORT = 11434  # GPU 1 (compute GPU, more work)
MODEL = "deepseek-v2:16b"

ENTITY_KEYS = [
    "ticker", "company", "person", "sector", "country", "event",
    "economic", "policy", "central_bank", "commodity", "crypto",
    "index", "geopolitical", "source", "rating", "metric",
]

PROMPT_TEMPLATE = """You are a financial analyst expert in stock market trading.

Task (in order):
1) Extract key entities from the tweet into the specified entity lists.
2) Write a new_summary (1-2 sentences) grounded in extracted entities.
3) Assign sentiment_score from 0.0 to 5.0 (Neutral is 2.5):
   0 Extremely Bearish, 1 Bearish, 2 Slightly Bearish, 3 Neutral, 4 Bullish, 5 Extremely Bullish
4) Provide brief reasoning (1-3 short sentences).

Tweet: {tweet}

Entity List:
ticker
company
person
sector
country
event
economic
policy
central_bank
commodity
crypto
index
geopolitical
source
rating
metric


Return ONLY valid JSON:
{{"key_entities":{{"ticker":[],"company":[],"person":[],"sector":[],"country":[],"event":[],"economic":[],"policy":[],"central_bank":[],"commodity":[],"crypto":[],"index":[],"geopolitical":[],"source":[],"rating":[],"metric":[]}},"new_summary":"","sentiment_score":0.0,"reasoning":""}}"""


def wait_healthy(port, timeout_s=30):
    """Wait for Ollama server to be healthy."""
    url = f"http://127.0.0.1:{port}/api/tags"
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            time.sleep(1)
    return False


def ollama_generate(port, tweet):
    """Call Ollama generate API."""
    url = f"http://127.0.0.1:{port}/api/generate"
    prompt = PROMPT_TEMPLATE.format(tweet=tweet)
    r = requests.post(url, json={"model": MODEL, "prompt": prompt, "stream": False}, timeout=180)
    r.raise_for_status()
    return r.json().get("response", "")


def repair_json(s):
    """Fix common LLM JSON issues: trailing commas, single quotes, unquoted keys."""
    import re
    # Remove trailing commas before } or ]
    s = re.sub(r',\s*([}\]])', r'\1', s)
    # Replace single-quoted strings with double-quoted (simple cases)
    s = re.sub(r"'([^']*)'", r'"\1"', s)
    return s


def parse_response(content):
    """Extract JSON from Ollama response with repair fallback."""
    if "{" in content and "}" in content:
        json_str = content[content.index("{"):content.rindex("}") + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return json.loads(repair_json(json_str))
    return None


def get_last_datetime():
    """Read walter_openai.csv to find last processed date+time."""
    last_dt = ""
    with open(WALTER_OPENAI_CSV, "r") as f:
        reader = csv.reader(f, delimiter="|")
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 2:
                dt = f"{row[0]} {row[1]}".strip()
                if dt > last_dt:
                    last_dt = dt
    return last_dt


def get_new_rows(after_dt):
    """Get rows from walter.csv with date+time > after_dt."""
    rows = []
    with open(WALTER_CSV, "r") as f:
        reader = csv.reader(f, delimiter="|")
        next(reader)
        for row in reader:
            if len(row) >= 3:
                dt = f"{row[0]} {row[1]}".strip()
                if dt > after_dt:
                    rows.append(row)
    return rows


def assign_row_ids(rows):
    """Assign daily-reset row_ids."""
    current_date = ""
    row_id = 0
    result = []
    for row in rows:
        if row[0] != current_date:
            row_id = 0
            current_date = row[0]
        result.append((row, row_id))
        row_id += 1
    return result


def format_output_row(date, time_str, description, row_id, parsed, api_error):
    """Format a single output row matching walter_openai.csv schema."""
    if parsed:
        entities = parsed.get("key_entities", {})
        entity_vals = [",".join(entities.get(k, [])) for k in ENTITY_KEYS]
        new_summary = parsed.get("new_summary", "")
        sentiment = parsed.get("sentiment_score", 0.0)
        reasoning = parsed.get("reasoning", "")
    else:
        entity_vals = [""] * len(ENTITY_KEYS)
        new_summary = ""
        sentiment = ""
        reasoning = ""
    return [date, time_str, description, str(row_id)] + entity_vals + [new_summary, str(sentiment), reasoning, api_error]


FLUSH_BATCH = 50  # flush to disk every N rows per GPU to avoid data loss


def process_chunk(port, gpu_id, chunk, progress):
    """Process a chunk of rows on a single GPU, flushing periodically."""
    batch = []
    for i, (row, row_id) in enumerate(chunk):
        date, time_str, description = row[0], row[1], row[2]
        api_error = ""
        parsed = None

        try:
            content = ollama_generate(port, description)
            parsed = parse_response(content)
            if parsed is None:
                api_error = "No JSON in response"
        except Exception as e:
            api_error = str(e)[:100]

        output_row = format_output_row(date, time_str, description, row_id, parsed, api_error)
        batch.append(output_row)

        progress["done"] += 1
        done = progress["done"]
        total = progress["total"]
        elapsed = time.time() - progress["t0"]
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        pct = done * 100 // total
        filled = 40 * done // total
        bar = "█" * filled + "░" * (40 - filled)
        err_count = progress["errors"]
        err_str = f" ERR:{err_count}" if err_count else ""
        print(f"\r  [{bar}] {pct}% {done}/{total} | {rate:.1f}/s | ETA {eta:.0f}s{err_str}   ", end="", flush=True)

        if api_error:
            progress["errors"] += 1

        # Periodic flush to avoid losing work on long runs
        if len(batch) >= FLUSH_BATCH:
            with progress["lock"]:
                flush(batch)
            batch = []

    # Flush remaining
    if batch:
        with progress["lock"]:
            flush(batch)

    return len(chunk)


def flush(rows):
    """Append rows to walter_openai.csv."""
    with open(WALTER_OPENAI_CSV, "a", newline="") as f:
        writer = csv.writer(f, delimiter="|")
        for row in rows:
            writer.writerow(row)


def main():
    # Health checks
    print("Checking GPU servers...")
    if not wait_healthy(GPU1_PORT):
        print(f"ERROR: Ollama on port {GPU1_PORT} not healthy")
        sys.exit(1)
    print(f"  GPU1 (port {GPU1_PORT}): OK")

    if not wait_healthy(GPU0_PORT):
        print(f"ERROR: Ollama on port {GPU0_PORT} not healthy")
        sys.exit(1)
    print(f"  GPU0 (port {GPU0_PORT}): OK")

    last_dt = get_last_datetime()
    print(f"Last processed datetime: {last_dt}")

    new_rows = get_new_rows(last_dt)
    total = len(new_rows)
    print(f"New rows to process: {total}")

    if total == 0:
        print("Nothing to process.")
        return

    rows_with_ids = assign_row_ids(new_rows)

    # 40/60 split: GPU0 (display) gets less, GPU1 (compute) gets more
    split = int(total * 0.40)
    chunk0 = rows_with_ids[:split]
    chunk1 = rows_with_ids[split:]
    print(f"GPU0: {len(chunk0)} rows (port {GPU0_PORT}) | GPU1: {len(chunk1)} rows (port {GPU1_PORT})")

    progress = {"done": 0, "total": total, "errors": 0, "t0": time.time(), "lock": threading.Lock()}

    with ThreadPoolExecutor(max_workers=2) as ex:
        f0 = ex.submit(process_chunk, GPU0_PORT, 0, chunk0, progress)
        f1 = ex.submit(process_chunk, GPU1_PORT, 1, chunk1, progress)
        f0.result()
        f1.result()

    print()  # newline after progress bar

    elapsed = time.time() - progress["t0"]
    errors = progress["errors"]
    print(f"Done. Appended {total} rows in {elapsed:.1f}s ({total / elapsed:.1f} rows/s) | Errors: {errors}")


if __name__ == "__main__":
    main()