# AssetFlow

AssetFlow is a local screenshot-driven investment ledger. The MVP receives iPhone Shortcut uploads on the same Wi-Fi network, recognizes 华泰涨乐全球通 screenshots, stores a SQLite ledger, reconciles positions, and exports transactions using the provided xlsx template.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn assetflow.main:app --host 0.0.0.0 --port 8787
```

The upload endpoint is `POST /api/uploads/ios-shortcut`.
