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

Dashboard UI:

```powershell
Start-Process http://127.0.0.1:8787/ui
```

The local dashboard supports web screenshot upload, candidate review, transaction and position views, cash movement entry, and XLSX export.
The dashboard is a trusted local UI; do not expose it on production or untrusted networks. For single-computer use, bind to `127.0.0.1`.

Upload endpoint:

```text
POST http://电脑局域网IP:8787/api/uploads/ios-shortcut
Header: X-AssetFlow-Token
Form fields: broker=htsc_global, file=<screenshot>
```

iPhone setup is documented in `docs/ios-shortcut.md`.

## Local OCR

AssetFlow supports a local PaddleOCR provider for first-pass offline OCR. PaddlePaddle may not provide Windows wheels for the newest Python versions. On Windows, use Python 3.13 or 3.12 instead of Python 3.14:

```powershell
conda create -n assetflow-ocr python=3.13
conda activate assetflow-ocr
python -m pip install --upgrade pip
pip install -e ".[dev,ocr]"
```

If your current Python environment can install PaddlePaddle, this is enough:

```powershell
pip install -e ".[dev,ocr]"
```

Then set `.env`:

```dotenv
ASSETFLOW_RECOGNITION_PROVIDER=paddleocr
```

Restart Uvicorn after changing `.env`. This first version defaults to PP-OCRv4 mobile on CPU with MKL-DNN disabled for better Windows compatibility, supports both PaddleOCR 3.x `predict()` results and 2.x `ocr()` results, then parses common 华泰涨乐全球通成交记录 text into transactions. Positions and cash screenshots are classified but still need follow-up parser work.
