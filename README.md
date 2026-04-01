# Allure TestOps Importer
### Made with much love by Dzmitry Mialeshka & Orlin Hernandez @ Hubstaff — Enjoy!

A tool for importing test cases from a CSV file into Allure TestOps.
Available as a **web UI** (recommended, no terminal needed) or a **CLI** for power users.

---

## Before you start — one-time setup

You only need to do this once on your machine.

### 1. Install Python

Check if you already have it:
```bash
python --version
```

If you get an error, download and install Python from https://www.python.org/downloads/

> **Windows users:** during installation, check the box that says **"Add Python to PATH"**

### 2. Install the required libraries

Open a terminal, navigate to the project folder, and run:
```bash
pip install requests python-dotenv pyyaml flask
```

### 3. Create your credentials file

In the project folder, create a file named `env.env` with the following content:
```
ALLURE_URL=https://your-allure-instance.com
ALLURE_TOKEN=your-api-token-here
```

> **Where do I get the token?**
> In Allure TestOps go to **Profile → API Tokens → Generate new token**, then copy it here.
> Never share this file or commit it to Git — it's already in `.gitignore`.

### 4. Set up your config file

Open `config.yml` and fill in:
- `url` — your Allure instance URL (e.g. `https://allure.yourcompany.com`)
- `project.id` — the numeric ID of your Allure project (visible in the URL when you open the project)
- `columns` — match these to your CSV column headers exactly (they are case-sensitive)

---

## Option A — Web UI (recommended)

No terminal knowledge required. Works on Mac and Windows.

### Start the app
```bash
python app.py
```

Then open your browser and go to: **http://localhost:5000**

Share this URL with teammates while the app is running — they can use it too.

### How it works

**Step 1 — Upload**
Drag and drop your CSV (exported from Google Sheets or Excel) onto the upload zone.
The app parses the file and automatically checks Allure for duplicates.

**Step 2 — Review**
A preview table shows every test case: name, precondition, steps, expected result, and whether it will be imported or skipped.
- 🟡 `skip` — already exists in Allure, will not be duplicated
- 🟢 `import` — new, will be created

Use **🔍 Dry Run** to see exactly what would happen without touching Allure.
Use **↺ Re-check duplicates** if you deleted test cases in Allure and want to refresh the status.

**Step 3 — Import**
Click **Import to Allure**. A live log shows `[ok]`, `[skip]`, or `[fail]` for each test case, with a summary at the end.

---

## Option B — CLI (power users)

### Every time you want to import

**Step 1 — Convert your CSV**

Parses your raw CSV and prepares it for Allure. Does not touch Allure at all.
```bash
python importer.py convert --input test_cases.csv --output converted.csv
```
Open `converted.csv` and check the `parsed_steps` column before continuing.

**Step 2 — Dry run**

Connects to Allure to check for duplicates, then prints everything that *would* be created — without making any changes.
```bash
python importer.py import --input converted.csv --dry-run
```

**Step 3 — Import**
```bash
python importer.py import --input converted.csv
```

The tool will print `[ok]`, `[skip]`, or `[fail]` for each test case.

### All CLI commands

| Command | What it does |
|---|---|
| `python importer.py init-config` | Generate a default `config.yml` |
| `python importer.py convert --input FILE --output FILE` | Parse CSV and prepare it for import |
| `python importer.py import --input FILE` | Import into Allure |
| `python importer.py import --input FILE --dry-run` | Preview import without making changes |
| `python importer.py import --input FILE --config FILE` | Use a custom config file |

---

## Formatting rules for your CSV

The tool understands two formats for **Precondition** and **Expected Result** columns:

**Numbered list** — each item gets its own line in Allure:
```
1. User is logged in 2. Project is open 3. Feature flag is enabled
```

**Bullet list** — each `*` becomes a bullet point in Allure:
```
* User is logged in * Project is open * Feature flag is enabled
```

**Scenario steps** — numbered list, each number becomes a separate step in Allure:
```
1. Open the dashboard 2. Click on Settings 3. Verify the page loads
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'yaml'`**
Run `pip install pyyaml` and try again.

**`ModuleNotFoundError: No module named 'flask'`**
Run `pip install flask` and try again.

**`[error] Missing ALLURE_URL or ALLURE_TOKEN`**
Check that your `env.env` file exists in the project folder and has both variables filled in.

**`[error] Missing columns: {'name', 'precondition'}`**
Your CSV headers don't match what's in `config.yml`. Open `config.yml`, find the `columns:` section, and update the values to match your CSV headers exactly (including capitalisation).

**`[skip]` on everything**
The test cases already exist in Allure. Delete them in Allure, then click **↺ Re-check duplicates** in the web UI, or re-run the CLI import.

**Steps not parsing / `step_count: 0`**
Make sure your Scenario column uses either `1. step one 2. step two` or `[step 1] step one [step 2] step two` format.

**Duplicate warning not clearing after deleting from Allure**
Click **↺ Re-check duplicates** in the web UI to refresh the duplicate status without re-uploading the file.