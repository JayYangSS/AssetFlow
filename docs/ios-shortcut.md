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
