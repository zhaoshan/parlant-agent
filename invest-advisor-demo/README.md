# invest-advisor-demo · 智能投顾 Demo 三方服务

「智能投顾 Agent」需求文档（`docs/05-sample-agents/智能投顾Agent需求.md`）中的**三方服务应用**：
独立 FastAPI 服务，文件存储（JSON）模拟后端，供 Parlant remote 工具调用。

## 启动

```bash
cd invest-advisor-demo
uv sync
.venv/bin/python -m app.main        # http://127.0.0.1:8300/docs
```

首次启动自动生成 `data/*.json` 种子数据（客户 / 产品 / 行情），后续重启保持。

## 接口一览

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/customer/{id}` | GET | 客户画像（标签、是否已测评、风险等级、VIP/专业） |
| `/risk/assess` | POST | 提交风险测评（简化：客户自报 C1~C5） |
| `/products?risk_level=C3` | GET | 按风险等级返回适配产品（含该等级及更低） |
| `/market/data?symbol=黄金` | GET | 模拟行情（随机微调；后续可接 Brave Search） |
| `/trade/order` | POST | 提交订单，返回确认号（本地 JSON 存储） |
| `/human/transfer` | POST | 转人工，返回随机工号 |

## 数据文件（data/，不入库）

- `customers.json` — 用户信息、`risk_assessed`、`risk_level`、VIP/专业标签
- `products.json` — 产品清单 + 每产品所属风险级别（C1~C5）
- `orders.json` — 订单提交记录
- `market.json` — 行情种子（价格随机微调）
- `transfers.json` — 转人工记录（随机工号）

## 与 Parlant 对接

6 个业务工具在 Agent schema（`parlant-agent-runtime/examples/inv-advisor-demo.json`）
里声明为 **remote 工具**，走平台通用 HTTP 工具内核（`parlant-agent-runtime/app/services/http_tools.py`）：
`method/url/headers` 在 schema 声明，请求时自动注入当前会话 `customer_id`（URL 用
`{customer_id}` 占位做路径参数）。POST 类工具 body 由工具参数填充。
