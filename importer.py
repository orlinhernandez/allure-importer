"""
Allure TestOps Importer — CLI Tool
Usage:
    python importer.py convert --input raw.csv --output converted.csv
    python importer.py import  --input converted.csv [--dry-run] [--config config.yml]
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

# ── DEFAULTS ──────────────────────────────────────────────────────────────────
DEFAULT_CONFIG_PATH = "config.yml"

# ── TOKEN PARSING ─────────────────────────────────────────────────────────────
TOKEN_PATTERN = re.compile(
    r"\s*\[(shared \d+|step \d+(?:\.\d+)?|expected \d+\.\d+|expected\.step \d+\.\d+\.\d+)\]\s*"
)
SKIP_PATTERN = re.compile(r"^(shared \d+|step \d+(\.\d+)?)$", re.IGNORECASE)


# ── CONFIG ────────────────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        print(f"[error] Config file not found: {config_path}")
        print("        Create one with: python importer.py init-config")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def write_default_config(path: str):
    template = """\
# Allure TestOps Importer — Config
# Copy this file, fill in your values, and pass it via --config

allure:
  url: https://your-allure-instance.com   # ALLURE_URL env var overrides this
  token_env: ALLURE_TOKEN                 # name of the env var holding your API token

project:
  id: 34

# Optional: map CSV column values to Allure custom fields
# Each entry needs the Allure customFieldValue id and the CSV column to read from
custom_fields:
  - id: 70
    name: "Insights"
    custom_field_id: -2
    custom_field_name: "Feature"
  - id: 5161
    name: "Remote vs In-office Benchmarks"
    custom_field_id: -3
    custom_field_name: "Story"

# CSV column names (change if your CSV uses different headers)
columns:
  name: name
  precondition: precondition
  expected_result: expected_result
  scenario: scenario
  description: description
  automated: automated
  tag: tag
  lead: Lead
  owner: Owner
"""
    Path(path).write_text(template, encoding="utf-8")
    print(f"  Default config written to: {path}")
    print("  Edit it with your project settings, then run convert/import.\n")


# ── AUTH ──────────────────────────────────────────────────────────────────────

def get_jwt_token(allure_url: str, token: str) -> str:
    print("Authenticating with Allure TestOps...")
    resp = requests.post(
        f"{allure_url}/api/uaa/oauth/token",
        data={"grant_type": "apitoken", "scope": "openid", "token": token},
        headers={"Accept": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    jwt = resp.json().get("access_token")
    if not jwt:
        print("  [error] Failed to get JWT token.")
        sys.exit(1)
    print("  Authenticated\n")
    return jwt


def get_headers(jwt: str) -> dict:
    return {"Content-Type": "application/json", "Authorization": f"Bearer {jwt}"}


# ── DUPLICATE DETECTION ───────────────────────────────────────────────────────

def fetch_existing_names(allure_url: str, project_id: int, headers: dict) -> set[str]:
    """Return a set of lowercased test case names already in the project."""
    print("Fetching existing test case names for duplicate detection...")
    names = set()
    page, size = 0, 100
    while True:
        resp = requests.get(
            f"{allure_url}/api/rs/testcase",
            params={"projectId": project_id, "page": page, "size": size},
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  [warn] Could not fetch existing test cases: {resp.status_code}. Skipping duplicate check.")
            return set()
        data = resp.json()
        items = data.get("content", [])
        for item in items:
            n = item.get("name", "")
            if n:
                names.add(n.strip().lower())
        if data.get("last", True):
            break
        page += 1
    print(f"  Found {len(names)} existing test cases\n")
    return names


# ── PARSING / FORMATTING ──────────────────────────────────────────────────────

def format_bullets(text: str) -> str:
    """Convert '* item1 * item2' style into one bullet per line."""
    if not text:
        return text
    items = re.split(r"(?:^|\s)\*\s*", text.strip())
    items = [i.strip() for i in items if i.strip()]
    if len(items) <= 1:
        return text  # no bullet structure, return as-is
    return "\n".join(f"* {i}" for i in items)


def format_numbered_lines(text: str) -> str:
    """Convert '1. item 2. item' into one item per line (strips numbers)."""
    if not text:
        return text
    parts = re.split(r"\s*\d+\.\s+", text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        return text  # no numbered structure, return as-is
    return "\n".join(parts)


def format_field(text: str) -> str:
    """Auto-detect format (numbered or bullet) and apply the right formatter."""
    if not text:
        return text
    if re.match(r"^\s*\d+\.\s+", text):
        return format_numbered_lines(text)
    return format_bullets(text)


def parse_scenario(scenario_raw: str) -> list[str]:
    if not scenario_raw or not scenario_raw.strip():
        return []

    # Format 1: [step X] tokens
    if re.search(r"\[step \d+", scenario_raw, re.IGNORECASE):
        pattern = re.compile(
            r"\[(shared \d+|step \d+(?:\.\d+)?|expected \d+\.\d+|expected\.step \d+\.\d+\.\d+)\]\s*(.*?)(?=\s*\[(?:shared|step|expected)|$)",
            re.DOTALL,
        )
        steps = []
        for token, text in pattern.findall(scenario_raw.strip()):
            text = text.strip()
            if not text:
                continue
            if SKIP_PATTERN.match(text):
                continue
            if text.lower() == "expected result":
                continue
            if re.match(r"expected \d+\.\d+$", token) or token.startswith("expected.step"):
                continue
            steps.append(text)
        return steps

    # Format 2: numbered steps "1. ... 2. ... 3. ..."
    numbered = re.split(r"\s*\d+\.\s+", scenario_raw.strip())
    steps = [s.strip() for s in numbered if s.strip()]
    return steps


# ── CONVERT COMMAND ───────────────────────────────────────────────────────────

def cmd_convert(args):
    """Read raw CSV, parse scenarios into step lists, write a clean converted CSV."""
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"[error] Input file not found: {input_path}")
        sys.exit(1)

    print(f"Converting: {input_path} → {output_path}\n")

    with open(input_path, newline="", encoding="utf-8") as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = "excel-tab" if "\t" in sample[:200] else "excel"
        print(f"  Detected format: {'tab-separated' if dialect == 'excel-tab' else 'comma-separated'}")
        reader = csv.DictReader(f, dialect=dialect)
        rows = list(reader)

    if not rows:
        print("[error] No rows found in input CSV.")
        sys.exit(1)

    print(f"  Rows to convert: {len(rows)}\n")

    # Only keep columns Allure needs (case-insensitive match)
    ALLURE_KEYS = {"name", "precondition", "expected_result", "description",
                   "automated", "tag", "lead", "owner"}
    keep = [c for c in rows[0].keys() if c.lower().replace(" ", "_") in ALLURE_KEYS]
    out_columns = keep + ["parsed_steps", "step_count"]

    out_rows = []
    for row in rows:
        scenario = row.get("scenario", "") or row.get("Scenario", "")
        steps = parse_scenario(scenario)
        out_row = {col: row.get(col, "") for col in keep}
        out_row["parsed_steps"] = json.dumps(steps)
        out_row["step_count"] = len(steps)
        out_rows.append(out_row)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_columns)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"  Converted {len(out_rows)} rows → {output_path}")
    print("  Review the file (especially 'parsed_steps') before importing.\n")


# ── IMPORT COMMAND ────────────────────────────────────────────────────────────

def build_custom_fields_payload(cfg: dict) -> list:
    return [
        {
            "id": cf["id"],
            "name": cf["name"],
            "customField": {
                "id": cf["custom_field_id"],
                "name": cf["custom_field_name"],
            },
        }
        for cf in cfg.get("custom_fields", [])
    ]


def build_labels(row: dict, col_cfg: dict) -> list:
    labels = []
    for col_key, label_name in [("tag", "tag"), ("lead", "lead"), ("owner", "owner")]:
        col = col_cfg.get(col_key, col_key)
        val = row.get(col, "").strip()
        if val:
            labels.append({"name": label_name, "value": val})
    return labels


def add_steps(tc_id: int, steps: list[str], headers: dict, allure_url: str, dry_run: bool):
    if dry_run:
        for s in steps:
            print(f"      [dry-run] step: {s[:80]}")
        return
    url = f"{allure_url}/api/rs/testcase/step"
    for text in steps:
        payload = {
            "testCaseId": tc_id,
            "bodyJson": {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
            },
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code not in [200, 201]:
            print(f"      [warn] Step failed '{text[:50]}': {resp.status_code} {resp.text[:150]}")


def create_test_case(
    row: dict,
    headers: dict,
    cfg: dict,
    custom_fields: list,
    existing_names: set,
    dry_run: bool,
) -> str:
    """Returns 'created', 'skipped', or 'failed'."""
    col = cfg.get("columns", {})
    allure_url = cfg["allure"]["url"]
    project_id = cfg["project"]["id"]

    name     = row.get(col.get("name", "name"), "").strip()
    pre      = format_field(row.get(col.get("precondition", "precondition"), "").strip())
    expected = format_field(row.get(col.get("expected_result", "expected_result"), "").strip())
    desc     = row.get(col.get("description", "description"), "").strip()
    auto_raw = row.get(col.get("automated", "automated"), "FALSE").strip().upper()
    automated = auto_raw == "TRUE"
    labels   = build_labels(row, col)

    # Steps: prefer pre-parsed column, fall back to live parse
    if "parsed_steps" in row and row["parsed_steps"].strip():
        try:
            steps = json.loads(row["parsed_steps"])
        except json.JSONDecodeError:
            steps = parse_scenario(row.get(col.get("scenario", "scenario"), ""))
    else:
        steps = parse_scenario(row.get(col.get("scenario", "scenario"), ""))

    # Duplicate check
    if name.lower() in existing_names:
        print(f"  [skip] Already exists: {name[:70]}")
        return "skipped"

    if dry_run:
        print(f"  [dry-run] Would create: {name[:70]}")
        print(f"    automated={automated}  labels={[l['value'] for l in labels]}")
        if pre:
            print(f"    precondition:")
            for line in pre.splitlines():
                print(f"      {line}")
        if expected:
            print(f"    expected result:")
            for line in expected.splitlines():
                print(f"      {line}")
        if steps:
            print(f"    steps ({len(steps)}):")
            for s in steps:
                print(f"      - {s[:80]}")
        return "created"

    payload = {
        "name":           name,
        "projectId":      project_id,
        "automated":      automated,
        "description":    desc,
        "precondition":   pre,
        "expectedResult": expected,
        "labels":         labels,
        "customFields":   custom_fields,
    }

    try:
        resp = requests.post(f"{allure_url}/api/rs/testcase", json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        tc_id = resp.json().get("id")
        print(f"  [ok] {name[:70]} → ID {tc_id}")
        add_steps(tc_id, steps, headers, allure_url, dry_run=False)
        return "created"
    except requests.HTTPError as e:
        print(f"  [fail] {name[:70]}")
        print(f"    {e.response.status_code}: {e.response.text[:300]}")
        return "failed"
    except Exception as e:
        print(f"  [error] {name[:70]} → {e}")
        return "failed"


def cmd_import(args):
    cfg = load_config(args.config)

    # Resolve Allure URL + token
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "env.env")
    load_dotenv(_env)
    allure_url = os.getenv("ALLURE_URL") or cfg["allure"].get("url", "")
    token_env  = cfg["allure"].get("token_env", "ALLURE_TOKEN")
    allure_token = os.getenv(token_env)

    if not allure_url or not allure_token:
        print(f"[error] Missing ALLURE_URL or {token_env} environment variable.")
        sys.exit(1)

    cfg["allure"]["url"] = allure_url.rstrip("/")
    project_id = cfg["project"]["id"]
    custom_fields = build_custom_fields_payload(cfg)

    dry_run = args.dry_run
    if dry_run:
        print("=== DRY RUN — no changes will be made to Allure ===\n")

    # Auth (skip in dry-run to allow offline testing)
    if dry_run:
        headers = {}
        existing_names = set()
    else:
        jwt = get_jwt_token(allure_url, allure_token)
        headers = get_headers(jwt)
        existing_names = fetch_existing_names(allure_url, project_id, headers)

    # Read input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[error] Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path, newline="", encoding="utf-8") as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = "excel-tab" if "\t" in sample[:200] else "excel"
        reader = csv.DictReader(f, dialect=dialect)
        rows = list(reader)

    if not rows:
        print("[error] No rows found in CSV.")
        sys.exit(1)

    col_cfg = cfg.get("columns", {})
    name_col = col_cfg.get("name", "name")
    required = {name_col, col_cfg.get("precondition", "precondition"),
                col_cfg.get("expected_result", "expected_result")}
    missing = required - set(rows[0].keys())
    if missing:
        print(f"[error] Missing columns: {missing}")
        print(f"        Columns found: {list(rows[0].keys())}")
        sys.exit(1)

    print(f"Importing {len(rows)} test cases from {input_path}...\n")
    counts = {"created": 0, "skipped": 0, "failed": 0}

    for i, row in enumerate(rows, 1):
        name = row.get(name_col, "unnamed")
        print(f"[{i}/{len(rows)}] {name[:70]}")
        result = create_test_case(row, headers, cfg, custom_fields, existing_names, dry_run)
        counts[result] += 1

    print(f"\n{'='*50}")
    label = "DRY RUN SUMMARY" if dry_run else "IMPORT SUMMARY"
    print(f"  {label}")
    print(f"  created: {counts['created']}   skipped: {counts['skipped']}   failed: {counts['failed']}")
    if dry_run:
        print("\n  Run without --dry-run to apply changes.")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="importer",
        description="Allure TestOps CSV Importer",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init-config
    p_init = sub.add_parser("init-config", help="Write a default config.yml to get started")
    p_init.add_argument("--output", default=DEFAULT_CONFIG_PATH, help="Where to write the config (default: config.yml)")

    # convert
    p_conv = sub.add_parser("convert", help="Parse raw CSV and write a clean converted CSV for review")
    p_conv.add_argument("--input",  required=True, help="Raw input CSV")
    p_conv.add_argument("--output", required=True, help="Converted output CSV")

    # import
    p_imp = sub.add_parser("import", help="Import converted CSV into Allure TestOps")
    p_imp.add_argument("--input",   required=True,            help="CSV to import (raw or converted)")
    p_imp.add_argument("--config",  default=DEFAULT_CONFIG_PATH, help="Config YAML (default: config.yml)")
    p_imp.add_argument("--dry-run", action="store_true",      help="Print what would be imported, no API calls")

    args = parser.parse_args()

    if args.command == "init-config":
        write_default_config(args.output)
    elif args.command == "convert":
        cmd_convert(args)
    elif args.command == "import":
        cmd_import(args)


if __name__ == "__main__":
    main()