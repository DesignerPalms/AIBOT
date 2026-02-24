# Trade Show Sales Analyzer (Streamlit Prototype)

Analyze trade show sales from an Excel file (`Show`, `Year`, `GrossSales`) with filters, KPIs, charts, and a safe AI query-plan router.

## Expected Excel format
First sheet is loaded by default and must include:
- `Show`
- `Year`
- `GrossSales`

Example:

| Show | Year | GrossSales |
|---|---:|---:|
| CES | 2022 | 120000 |
| CES | 2023 | $145,500 |
| NRF | 2023 | 98000 |

## Run locally
```bash
python -m venv venv
source venv/bin/activate  # Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## API key setup (optional AI mode)
The app reads `OPENAI_API_KEY` from:
1. `st.secrets["OPENAI_API_KEY"]` (recommended for Streamlit)
2. `os.environ.get("OPENAI_API_KEY")`

### Use `.streamlit/secrets.toml` (local)
Create:
```toml
# .streamlit/secrets.toml
OPENAI_API_KEY = "your_api_key_here"
```

`/.streamlit/secrets.toml` and `.env` are gitignored so local keys won't be committed.

### Use environment variable
macOS/Linux:
```bash
export OPENAI_API_KEY="your_api_key_here"
```

Windows PowerShell:
```powershell
setx OPENAI_API_KEY "your_api_key_here"
```

## Safe AI query plan design
When **Enable AI** is on:
- Model: `gpt-5-mini`
- The model returns **JSON plan only** (no code)
- App validates action + params against allowlist and bounds
- App runs trusted local pandas/matplotlib functions
- No `exec`/`eval` is used on model output

If AI output is invalid, app retries once, then falls back to manual parser.

## Supported actions and example questions
- `year_totals`
  - “show year totals”
- `top_shows`
  - “top 15 shows between 2021 and 2024”
- `show_trend`
  - “trend for CES”
- `yoy_by_show`
  - “yoy percent by show from 2020 to 2024”
- `return_after_break`
  - “which shows had the biggest return after a 2-year break?”
- `cohort_by_attendance_number`
  - “cohort by attendance number up to 6, normalized”

## Manual parser commands (AI off)
- `top shows`
- `trend <show name>`
- `year totals`
- `biggest yoy increase`


## Experimental: Full AI analysis (send data)
- Turn on **Experimental: Full AI analysis (send data)** in the sidebar.
- Warning: this sends your **filtered** `Show, Year, GrossSales` rows to the model.
- The app shows both:
  - **Local result** (trusted local pandas actions)
  - **AI result** (model-generated JSON answer, insights, tables, chart instructions)
- If filtered rows exceed 900, the app asks for confirmation before sending.
- CSV payload is capped at 200,000 characters to control token usage.

