# AssetFlow

AssetFlow is a local screenshot-driven investment ledger. The MVP receives iPhone Shortcut uploads on the same Wi-Fi network, recognizes 华泰涨乐全球通 screenshots, stores a SQLite ledger, reconciles positions, and exports transactions using the provided xlsx template.

## Local Run

```powershell
conda activate finacial
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn assetflow.main:app --host 0.0.0.0 --port 8787
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health
```

Upload endpoint:

```text
POST http://电脑局域网IP:8787/api/uploads/ios-shortcut
Header: X-AssetFlow-Token
Form fields: broker=htsc_global, file=<screenshot>
```

iPhone setup is documented in `docs/ios-shortcut.md`.
