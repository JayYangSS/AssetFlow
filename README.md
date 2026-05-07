# AssetFlow

AssetFlow 是一个本地运行的截图识别投资账本。它接收华泰涨乐全球通截图，通过 OCR 抽取交易和持仓信息，保存到本地 SQLite，并提供一个本地 Web UI 用来审核候选交易、补录缺失字段、查看持仓和交易流水、记录资金出入金、导出 xlsx。

> 这是本地可信工具，不要直接暴露到公网或不可信网络。

## 快速启动

推荐使用本项目一直使用的 conda 环境：

```powershell
conda activate assetflow-ocr
pip install -e ".[dev,ocr]"
Copy-Item .env.example .env
```

编辑 `.env`，至少确认下面两项：

```dotenv
ASSETFLOW_UPLOAD_TOKEN=change-me-token
ASSETFLOW_RECOGNITION_PROVIDER=paddleocr
```

本机查看时启动：

```powershell
uvicorn assetflow.main:app --host 127.0.0.1 --port 8787
```

如果要让 iPhone 快捷指令从同一 Wi-Fi 上传截图，改用局域网监听：

```powershell
uvicorn assetflow.main:app --host 0.0.0.0 --port 8787
```

打开 UI：

```powershell
Start-Process http://127.0.0.1:8787/ui
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8787/health
```

## 使用流程

1. 启动服务并打开 `http://127.0.0.1:8787/ui`。
2. 在“上传”页面上传截图，或用 iPhone 快捷指令上传。
3. 在“审核”页面查看 OCR 生成的候选交易。
4. 如果候选交易提示缺失字段，点“编辑”补充字段后再确认。
5. 确认后的记录进入“交易流水”。
6. 在“持仓”页面查看最新持仓；如果 OCR 漏掉数量、市值、市价等字段，可以点“编辑”补录，系统会按数量、市价、市值之间的关系自动补全可推导字段。
7. 在“资金流水”页面手动记录券商账户入金、出金、利息、税费等现金变动。
8. 在“导出”页面选择模板和币种，生成 xlsx 文件。

## UI 页面

- `/ui`：总览页，展示按币种汇总的持仓市值、现金余额和合计资产，并可查看最近上传截图。
- `/ui/upload`：浏览器上传截图，也可查看最近上传的原始图片。
- `/ui/review`：候选交易审核、编辑、确认、忽略。
- `/ui/transactions`：已确认交易流水，可按币种、股票代码过滤，并展示按 FIFO 计算的买卖已实现盈亏、分红收入、额外费用和总收益。
- `/ui/positions`：最新持仓快照，可编辑补录缺失字段。
- `/ui/cash`：手动录入和查看资金流水。
- `/ui/export`：按模板导出 xlsx。

## 支持的截图

当前本地 PaddleOCR 主要适配华泰涨乐全球通：

- 交易截图：
  - 成交记录
  - 订单列表里的“已成交”
  - 个股详情页的“交易明细”
- 持仓截图：
  - 港股持仓
  - 美股持仓
  - 截图不完整时，后续再次上传可以合并补充已识别字段
- 资金流水截图：
  - 入金记录
  - 出金记录

交易明细里的“中签”会按买入处理。若截图没有佣金和费用，华泰全球通默认佣金为 0，港股交易税费会按默认税费规则估算。

入金/出金记录截图会进入“审核”队列，代码为 `CASH`，确认后进入“资金流水”。无法从截图识别的现金变化仍可在“资金流水”页面手动录入。

## iPhone 快捷指令上传

接口：

```text
POST http://电脑局域网IP:8787/api/uploads/ios-shortcut
Header: X-AssetFlow-Token: .env 中的 ASSETFLOW_UPLOAD_TOKEN
Form fields:
  broker=htsc_global
  file=<screenshot>
```

详细配置见 [docs/ios-shortcut.md](docs/ios-shortcut.md)。

## 本地 OCR 环境

PaddlePaddle 在 Windows 上对最新 Python 版本的 wheel 支持可能滞后。推荐 Python 3.13 或 3.12：

```powershell
conda create -n assetflow-ocr python=3.13
conda activate assetflow-ocr
python -m pip install --upgrade pip
pip install -e ".[dev,ocr]"
```

如果已经在 `assetflow-ocr` 环境中，日常更新依赖只需要：

```powershell
conda activate assetflow-ocr
pip install -e ".[dev,ocr]"
```

`.env` 中启用本地 OCR：

```dotenv
ASSETFLOW_RECOGNITION_PROVIDER=paddleocr
```

修改 `.env` 后需要重启 Uvicorn。

## 数据文件

默认数据目录是 `./data`：

- `data/assetflow.db`：SQLite 数据库。
- `data/uploads/`：上传的原始截图。
- `data/exports/`：导出的 xlsx。

如果用 DB Browser 打开数据库并进入编辑状态，SQLite 可能会报 `database is locked`。上传或识别前请先保存并关闭 DB Browser 中的写入事务。

## 导出 xlsx

项目使用现有模板 `data/导入模板.xlsx` 或你在 UI 中指定的模板路径。导出时建议按币种分别导出，例如：

```text
assetflow-htsc_global-HKD.xlsx
assetflow-htsc_global-USD.xlsx
```

只有已确认交易会进入导出。缺少必填字段或模板不支持的记录会被跳过，并在导出结果中提示。

## 测试

```powershell
conda activate assetflow-ocr
pytest -q
```

如果需要避免 pytest 临时目录散落在系统临时目录，可以使用：

```powershell
pytest -q --basetemp .pytest-tmp
```
