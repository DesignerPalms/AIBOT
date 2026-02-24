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
- Ask a question in the main input box and the app will return a short AI text answer.
- In AI mode, the app sends the uploaded Excel file + your question directly to the model.
- No JSON contract is required for AI replies; response is plain text only.
- Supporting local data/charts are not auto-rendered in AI mode now (AI answer only).

- If AI returns empty text, open **AI debug details** in the app to inspect response status, output count, incomplete details, and token usage.
