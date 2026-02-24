# Trade Show Sales Analyzer (Streamlit Prototype)

Analyze trade show sales from an Excel file (`Show`, `Year`, `GrossSales`) with filters, KPIs, charts, and optional full-data AI analysis.

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

## AI analysis mode
- Turn on **Enable AI analysis (send filtered data)** in the sidebar.
- Warning: this sends your **filtered** `Show, Year, GrossSales` rows to the model.
- Ask a question in the main input box and the app will return:
  - short answer
  - key insights
  - relevant table(s) when available
  - relevant chart(s) when available
- If filtered rows exceed 900, the app asks for confirmation before sending.
- CSV payload is capped at 200,000 characters to control token usage.
- If structured JSON parsing fails, the app still shows the best available AI text response.
