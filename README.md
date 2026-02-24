# Trade Show Sales Analyzer (Streamlit Prototype)

A simple Streamlit app to analyze trade show sales from an Excel file.

## Expected Excel format
Upload an `.xlsx` file with these required columns (first sheet is used by default):

- `Show`
- `Year`
- `GrossSales`

### Example

| Show | Year | GrossSales |
|---|---:|---:|
| CES | 2022 | 120000 |
| CES | 2023 | $145,500 |
| NRF | 2023 | 98000 |

`GrossSales` can include `$` and `,` symbols; the app cleans and converts these values.

## Features

- Upload and validate `.xlsx` input
- Cleans and coerces data types:
  - `Year` -> integer
  - `GrossSales` -> float
- Drops rows with blank `Show` or missing `GrossSales` (and invalid `Year`)
- Global filters for `Show` and year range
- KPI cards:
  - Total Gross Sales
  - Number of unique shows
  - Best Year
  - Best Show
- Charts:
  - Total sales by year
  - Top N shows by sales
  - YoY change by show
- Ask box (command-based, no API key required):
  - `top shows`
  - `trend <show name>`
  - `year totals`
  - `biggest yoy increase`
- Optional AI mode (OpenAI) to map natural language to supported commands only
- Trust/debug panels for calculations and data quality

## Run locally

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Optional: Enable AI mode (OpenAI)

Set your API key before starting the app (either option works):

**Option A: `secrets.toml` next to `app.py`**

```toml
OPENAI_API_KEY = "your_api_key_here"
```

**Option B: environment variable**

```bash
export OPENAI_API_KEY="your_api_key_here"
```

Then enable **"Enable AI (OpenAI)"** in the sidebar.

The AI mode is constrained to return one of these actions only:
- `top_shows`
- `trend_show`
- `year_totals`
- `biggest_yoy_increase`

No arbitrary code execution is performed.
