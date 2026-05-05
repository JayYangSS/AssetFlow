# iPhone Shortcut Setup

## Prerequisites

- iPhone and AssetFlow computer are on the same Wi-Fi.
- AssetFlow is running with `uvicorn assetflow.main:app --host 0.0.0.0 --port 8787`.
- `.env` contains a strong `ASSETFLOW_UPLOAD_TOKEN`.

## Shortcut Actions

1. Create a new Shortcut named `Upload to AssetFlow`.
2. Enable "Show in Share Sheet".
3. Accept images as input.
4. Add "Get Contents of URL".
5. URL: `http://电脑局域网IP:8787/api/uploads/ios-shortcut`.
6. Method: `POST`.
7. Headers:
   - `X-AssetFlow-Token`: value from `.env`
8. Request Body: Form.
9. Form fields:
   - `broker`: Text, `htsc_global`
   - `file`: File, Shortcut Input
10. Save the Shortcut.

## Usage

1. Open 华泰涨乐全球通.
2. Take a screenshot of 成交记录, 持仓, or 资金 page.
3. Open the screenshot in Photos.
4. Share to `Upload to AssetFlow`.
5. Check AssetFlow review queue if the record is not auto-confirmed.

## Local OCR Mode

To use offline PaddleOCR instead of the fixture recognizer, install the OCR extra on the AssetFlow computer. PaddlePaddle may not provide Windows wheels for the newest Python versions. On Windows, use Python 3.13 or 3.12 instead of Python 3.14:

```powershell
conda create -n assetflow-ocr python=3.13
conda activate assetflow-ocr
python -m pip install --upgrade pip
pip install -e ".[dev,ocr]"
```

If PaddlePaddle is available in your current environment, this is enough:

```powershell
pip install -e ".[dev,ocr]"
```

Then set `.env`:

```dotenv
ASSETFLOW_RECOGNITION_PROVIDER=paddleocr
```

Restart Uvicorn after changing `.env`. The local OCR provider uses PP-OCRv4 mobile on CPU with MKL-DNN disabled for better Windows compatibility. For best results, configure the Shortcut to convert the shared image to PNG before sending it as the `file` form field.
