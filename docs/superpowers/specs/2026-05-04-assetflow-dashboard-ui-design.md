# AssetFlow 本地资产看板界面设计

## 背景

AssetFlow 当前已经具备截图上传、OCR 识别、候选交易生成、交易确认、持仓对账和 XLSX 导出的后端能力，但这些能力主要通过 API 和数据库表暴露。日常使用时，用户还需要手动查看 SQLite 数据库，不方便确认交易、查看持仓、录入资金变动和导出文件。

本设计定义第一版本地 Web 操作台。它不是公开多用户系统，而是运行在本机或局域网中的个人资产管理界面。

## 目标

- 提供总览优先的本地 Web 界面，作为 AssetFlow 的日常入口。
- 支持网页手动上传截图，同时保留 iPhone Shortcut 上传流程。
- 支持查看和处理候选交易，减少直接操作数据库的需求。
- 支持查看正式交易流水、最新持仓、最新现金快照。
- 支持手动录入入金、出金、分红、费用和调整等资金流水。
- 支持基于正式流水和最新现金/持仓截图进行资产展示和对账。
- 支持从界面触发 XLSX 导出。

## 非目标

- 不实现完整用户系统、账号权限、多人协作。
- 不做复杂图表、收益率归因、组合分析。
- 不在第一版实现候选交易的高级批量编辑。
- 不替代券商账户的最终账务记录；AssetFlow 仍以本地辅助台账为定位。

## 产品方向

第一版采用“总览优先”布局。

顶部导航包含：

- 总览
- 上传
- 审核
- 交易流水
- 持仓
- 资金流水
- 导出

总览页是默认首页，显示资产状态和待办入口。其他页面用于完成具体任务。

## 页面设计

### 总览

总览页显示：

- 总资产卡片：基于最新现金截图和最新持仓截图聚合。
- 现金卡片：按币种展示最新现金快照。
- 持仓市值卡片：按最新持仓快照聚合。
- 待审核卡片：显示 `pending` 和 `needs_review` 候选数量。
- 持仓摘要：股票代码、名称、数量、市值、盈亏、快照时间。
- 最近交易：最近正式入账的 `Transaction`。
- 最近上传：上传时间、截图类型、识别状态。
- 快捷操作：上传截图、处理审核、导出 XLSX、运行对账。

### 上传

上传页支持：

- 选择券商，第一版默认为 `htsc_global`。
- 填写可选账户别名。
- 上传截图文件。
- 上传完成后显示上传状态、是否重复、OCR 截图类型、识别到的交易/持仓/现金数量。

网页上传复用现有上传、识别、候选生成、自动确认和对账流程。iPhone Shortcut 上传接口继续保留。

### 审核

审核页显示候选交易。

默认展示：

- `pending`
- `needs_review`

可筛选查看：

- `confirmed`
- `ignored`
- `duplicate`

候选交易操作：

- 确认：调用确认逻辑，成功后写入正式 `Transaction`。
- 忽略：将候选标记为 `ignored`，不进入正式流水。
- 查看来源：显示上传 ID、OCR 结果 ID、识别置信度和原始识别摘要。

第一版对于字段不完整的候选，显示缺失字段提示。缺少 `net_amount` 的买卖候选不能自动确认；后续版本可增加编辑候选字段后确认。

### 交易流水

交易流水页展示正式 `Transaction`。

支持筛选：

- 日期范围
- 币种
- 股票代码
- 交易类型
- 账户别名

交易类型包括：

- `buy`
- `sell`
- `cash_in`
- `cash_out`
- `dividend`
- `fee`
- `adjustment`

买卖交易和资金流水共用正式流水表，但界面根据类型隐藏不相关字段。

### 持仓

持仓页展示最新 `PositionSnapshot`。

展示字段：

- 市场
- 股票代码
- 名称
- 数量
- 可用数量
- 成本价
- 市价
- 市值
- 未实现盈亏
- 币种
- 快照时间

第一版按最新快照展示，不做历史持仓曲线。

### 资金流水

资金流水页用于手动记录非买卖现金变动。

支持新增：

- 入金：`trade_type=cash_in`，`net_amount` 为正。
- 出金：`trade_type=cash_out`，`net_amount` 为负。
- 分红：`trade_type=dividend`，`net_amount` 为正。
- 费用：`trade_type=fee`，`net_amount` 通常为负。
- 调整：`trade_type=adjustment`，`net_amount` 可正可负。

第一版不新增单独的资金流水表，继续写入 `Transaction`：

- `symbol="CASH"`
- `security_name="Cash"`
- `quantity=0`
- `price=0`
- `net_amount` 记录真实现金变化
- `currency` 记录币种

现金截图 `CashSnapshot` 用于展示观察到的现金余额，并与流水推导结果对账。

### 导出

导出页支持：

- 输入模板路径
- 输入输出路径
- 选择币种
- 触发 XLSX 导出
- 展示导出行数和跳过的交易 ID

第一版沿用现有 xlsx 模板导出逻辑。

## 数据模型

第一版不新增核心账务表。

继续使用：

- `Upload`：上传文件记录。
- `OcrResult`：OCR 原始和标准化结果快照。
- `CandidateTransaction`：候选交易和审核队列。
- `Transaction`：正式流水，包括股票买卖和资金变动。
- `PositionSnapshot`：持仓截图快照。
- `CashSnapshot`：现金截图快照。
- `ReconciliationIssue`：对账差异。

`CandidateTransaction` 和 `Transaction` 的关系：

- OCR 识别结果先生成候选。
- 完整并可信的候选可以确认成正式流水。
- 字段不完整或置信度不足的候选留在审核页。
- 重复候选在生成阶段尽量跳过，历史重复候选可在界面中忽略。

`Transaction` 统一承载：

- 股票买卖
- 入金出金
- 分红费用
- 现金调整

## 后端接口

新增或补齐以下接口：

- `GET /ui`：总览页。
- `GET /ui/upload`：上传页。
- `GET /ui/review`：审核页。
- `GET /ui/transactions`：交易流水页。
- `GET /ui/positions`：持仓页。
- `GET /ui/cash`：资金流水页。
- `GET /ui/export`：导出页。
- `GET /api/dashboard/summary`：总览数据。
- `GET /api/transactions`：正式交易列表。
- `GET /api/positions/latest`：最新持仓列表。
- `GET /api/cash/latest`：最新现金快照。
- `GET /api/uploads`：最近上传列表。
- `POST /api/uploads/web`：网页上传截图。
- `POST /api/review/candidates/{candidate_id}/ignore`：忽略候选。
- `POST /api/cash/movements`：新增资金流水。

保留现有接口：

- `POST /api/uploads/ios-shortcut`
- `GET /api/review/candidates`
- `POST /api/review/candidates/{candidate_id}/confirm`
- `POST /api/reconcile`
- `POST /api/exports/xlsx`

## 前端实现方式

采用 FastAPI 服务端页面。

技术选型：

- Jinja2 模板渲染页面。
- 少量原生 JavaScript 或 HTMX 风格交互。
- 静态资源放在 `assetflow/static`。
- 模板放在 `assetflow/templates`。
- 在项目依赖中加入 `jinja2`。

理由：

- 当前项目已经是 FastAPI 后端。
- 本地单人使用，不需要复杂前端状态管理。
- 安装和运行简单，适合第一版快速落地。
- 后续如果需要复杂交互，可以再引入 React/Vite。

## 本地访问与安全

第一版按本地单人使用设计：

- 不实现登录。
- 保留上传 API 的 token 校验。
- UI 页面默认只建议绑定本机或可信局域网访问。

如果后续需要给局域网内长期访问，可增加简单密码登录。

## 错误处理

界面需要展示明确错误：

- 上传文件格式不支持。
- OCR Provider 未配置或运行失败。
- 候选字段不完整，无法确认。
- XLSX 模板路径不存在。
- 导出失败。
- SQLite 数据库被外部工具锁定。

错误信息应显示在当前页面顶部或操作按钮附近，不要求第一版实现全局通知系统。

## 测试策略

后端测试：

- 总览 API 聚合数据正确。
- 交易列表筛选正确。
- 最新持仓和现金快照选择正确。
- 网页上传复用现有上传流程。
- 忽略候选会更新 `review_status`。
- 新增资金流水会写入 `Transaction`，正负号符合类型。
- XLSX 导出接口从 UI 参数触发成功。

模板测试：

- 关键页面返回 200。
- 页面包含核心表格、表单和操作入口。

不要求第一版做浏览器端端到端测试。

## 第一版完成标准

- 启动 Uvicorn 后访问 `/ui` 能看到总览页。
- 可以从网页上传截图并看到识别结果摘要。
- 可以查看候选交易并确认完整候选。
- 可以忽略错误或历史重复候选。
- 可以查看正式交易流水。
- 可以查看最新持仓和最新现金快照。
- 可以手动新增入金/出金等资金流水。
- 可以从界面导出 XLSX。
