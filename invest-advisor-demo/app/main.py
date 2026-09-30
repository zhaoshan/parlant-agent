"""invest-advisor-demo：智能投顾 Demo 三方服务（模拟后端）。

独立 FastAPI 应用，文件存储（JSON）而非纯内存，演示数据可重启保持：
- data/customers.json   用户信息、是否已做风险测评、风险等级
- data/products.json    产品清单 + 每产品所属风险级别
- data/orders.json      订单提交记录
- data/market.json      行情（初始种子；每次请求随机微调）
- data/transfers.json   转人工记录

接口（见 docs/05-sample-agents/智能投顾Agent需求.md §3）：
    GET  /customer/{id}     客户画像（VIP/专业/风险等级等）
    POST /risk/assess       提交风险测评（简化：客户自报 C1~C5）
    GET  /products          按 risk_level 返回适配产品
    GET  /market/data       模拟行情（随机微调）
    POST /trade/order       提交订单，返回确认号
    POST /human/transfer    转人工，返回工单号

运行：
    uv sync && .venv/bin/python -m app.main    # http://127.0.0.1:8300/docs
"""

from __future__ import annotations

import asyncio
import json
import random
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from uvicorn import run

HOST = "127.0.0.1"
PORT = 8300
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

RISK_LEVELS = ["C1", "C2", "C3", "C4", "C5"]

# 种子数据：产品清单（风险级别 C1 保守 ~ C5 进取）
SEED_PRODUCTS: list[dict[str, Any]] = [
    {"id": "p_001", "name": "货币基金（天天宝）", "risk_level": "C1", "type": "货币基金", "expected_return": "2.0%"},
    {"id": "p_002", "name": "国债（1年期）", "risk_level": "C1", "type": "国债", "expected_return": "2.3%"},
    {"id": "p_003", "name": "纯债基金（稳健）", "risk_level": "C2", "type": "纯债基金", "expected_return": "3.1%"},
    {"id": "p_004", "name": "银行理财（固收+）", "risk_level": "C2", "type": "银行理财", "expected_return": "3.5%"},
    {"id": "p_005", "name": "混合型基金（平衡）", "risk_level": "C3", "type": "混合型基金", "expected_return": "5.2%"},
    {"id": "p_006", "name": "二级债基（增强）", "risk_level": "C3", "type": "二级债基", "expected_return": "4.8%"},
    {"id": "p_007", "name": "股票型基金（成长）", "risk_level": "C4", "type": "股票型基金", "expected_return": "8.5%"},
    {"id": "p_008", "name": "偏股混合（进取）", "risk_level": "C4", "type": "偏股混合", "expected_return": "9.0%"},
    {"id": "p_009", "name": "行业主题基金（科技）", "risk_level": "C5", "type": "行业主题", "expected_return": "12.0%"},
    {"id": "p_010", "name": "杠杆ETF（高风险）", "risk_level": "C5", "type": "杠杆产品", "expected_return": "18.0%"},
]

# 种子客户：两个演示用客户（一个普通、一个 VIP 专业）
SEED_CUSTOMERS: list[dict[str, Any]] = [
    {
        "id": "cus_001",
        "name": "张先生",
        "tags": [],
        "is_vip": False,
        "is_professional": False,
        "risk_assessed": False,
        "risk_level": None,
        "preferred_contact": "电话",
    },
    {
        "id": "cus_002",
        "name": "李女士",
        "tags": ["vip", "professional"],
        "is_vip": True,
        "is_professional": True,
        "risk_assessed": True,
        "risk_level": "C4",
        "preferred_contact": "邮件",
    },
]

SEED_MARKET: dict[str, Any] = {
    "symbols": {
        "沪深300": {"price": 4021.5, "unit": "点"},
        "纳斯达克": {"price": 17850.2, "unit": "点"},
        "黄金": {"price": 2385.4, "unit": "美元/盎司"},
        "原油": {"price": 78.3, "unit": "美元/桶"},
    }
}

SEED_ORDERS: list[dict[str, Any]] = []
SEED_TRANSFERS: list[dict[str, Any]] = []


# --------------------------------------------------------------------------
# 文件存储（线程安全：FastAPI 同步端点跑在线程池，读写需加锁）
# --------------------------------------------------------------------------
_lock = threading.Lock()
_cache: dict[str, list[dict[str, Any]] | dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _ensure_file(name: str) -> Path:
    path = DATA_DIR / name
    if not path.exists():
        seed: Any = {
            "customers.json": SEED_CUSTOMERS,
            "products.json": SEED_PRODUCTS,
            "orders.json": SEED_ORDERS,
            "market.json": SEED_MARKET,
            "transfers.json": SEED_TRANSFERS,
        }[name]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_table(name: str) -> list[dict[str, Any]]:
    """读 JSON 表（数组）。"""
    with _lock:
        path = _ensure_file(name)
        return json.loads(path.read_text(encoding="utf-8"))


def save_table(name: str, rows: list[dict[str, Any]]) -> None:
    with _lock:
        path = _ensure_file(name)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_market() -> dict[str, Any]:
    with _lock:
        path = _ensure_file("market.json")
        return json.loads(path.read_text(encoding="utf-8"))


def save_market(data: dict[str, Any]) -> None:
    with _lock:
        path = _ensure_file("market.json")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _gen_id(prefix: str, existing: list[dict[str, Any]]) -> str:
    """按既有 id 生成自增后缀：ord_0001、tk_0001…"""
    used = {
        int(row["id"].split("_")[-1]) for row in existing if "_" in row.get("id", "")
    }
    n = (max(used) + 1) if used else 1
    return f"{prefix}_{n:04d}"


# --------------------------------------------------------------------------
# 请求模型
# --------------------------------------------------------------------------
class RiskAssessBody(BaseModel):
    risk_level: str = Field(..., description="客户自报风险等级 C1~C5")
    customer_id: str = Field("", description="客户 id（remote 工具自动注入；也兼容 query 传参）")


class OrderBody(BaseModel):
    customer_id: str
    product_id: str
    amount: float = Field(..., gt=0, description="下单金额（元）")


class TransferBody(BaseModel):
    customer_id: str
    reason: str = "客户主动要求转人工"


# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------
app = FastAPI(title="invest-advisor-demo", version="0.1.0", description="智能投顾 Demo 三方服务（模拟数据）")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "invest-advisor-demo"}


@app.get("/customer/{customer_id}")
def get_customer(customer_id: str) -> dict[str, Any]:
    rows = load_table("customers.json")
    for c in rows:
        if c["id"] == customer_id:
            return c
    raise HTTPException(status_code=404, detail=f"客户不存在: {customer_id}")


@app.post("/risk/assess")
def assess_risk(body: RiskAssessBody, customer_id: str = "") -> dict[str, Any]:
    """提交风险测评（简化：客户自报 C1~C5）。

    customer_id 优先取 body（remote 工具自动注入），query 参数兼容；风险等级
    落 customers.json。
    """
    if body.risk_level not in RISK_LEVELS:
        raise HTTPException(status_code=400, detail=f"风险等级非法，应为 {RISK_LEVELS}")
    customer_id = body.customer_id or customer_id
    customers = load_table("customers.json")
    for c in customers:
        if c["id"] == customer_id:
            c["risk_assessed"] = True
            c["risk_level"] = body.risk_level
            save_table("customers.json", customers)
            return {"customer_id": customer_id, "risk_level": body.risk_level, "assessed_at": _now()}
    # 未找到客户则新建（演示友好）
    new_customer = {
        "id": customer_id,
        "name": "新客户",
        "tags": [],
        "is_vip": False,
        "is_professional": False,
        "risk_assessed": True,
        "risk_level": body.risk_level,
        "preferred_contact": "电话",
    }
    customers.append(new_customer)
    save_table("customers.json", customers)
    return {"customer_id": customer_id, "risk_level": body.risk_level, "assessed_at": _now()}


@app.get("/products")
def get_products(risk_level: str = "") -> dict[str, Any]:
    """按风险等级返回适配产品（含该等级及更低等级）。"""
    products = load_table("products.json")
    if risk_level:
        if risk_level not in RISK_LEVELS:
            raise HTTPException(status_code=400, detail=f"风险等级非法，应为 {RISK_LEVELS}")
        idx = RISK_LEVELS.index(risk_level)
        allowed = RISK_LEVELS[: idx + 1]
        products = [p for p in products if p["risk_level"] in allowed]
    return {"risk_level": risk_level, "count": len(products), "products": products}


@app.get("/market/data")
def get_market_data(symbol: str = "") -> dict[str, Any]:
    """模拟行情：随机微调当前价。symbol 空则返回全部。"""
    market = load_market()
    symbols = market["symbols"]
    if symbol and symbol not in symbols:
        raise HTTPException(status_code=404, detail=f"未知行情标的: {symbol}")
    targets = {symbol: symbols[symbol]} if symbol else symbols
    result: dict[str, Any] = {}
    for sym, info in targets.items():
        drift = random.uniform(-0.8, 0.8)
        result[sym] = {
            "symbol": sym,
            "price": round(info["price"] * (1 + drift / 100), 2),
            "unit": info["unit"],
            "change_pct": round(drift, 2),
        }
    return {"count": len(result), "quotes": result}


@app.post("/trade/order")
def place_order(body: OrderBody) -> dict[str, Any]:
    """提交订单，本地 JSON 存储，返回确认号。"""
    customers = load_table("customers.json")
    products = load_table("products.json")
    if not any(c["id"] == body.customer_id for c in customers):
        raise HTTPException(status_code=404, detail=f"客户不存在: {body.customer_id}")
    product = next((p for p in products if p["id"] == body.product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail=f"产品不存在: {body.product_id}")
    orders = load_table("orders.json")
    order_id = _gen_id("ord", orders)
    row = {
        "id": order_id,
        "customer_id": body.customer_id,
        "product_id": body.product_id,
        "product_name": product["name"],
        "risk_level": product["risk_level"],
        "amount": body.amount,
        "status": "confirmed",
        "created_at": _now(),
    }
    orders.append(row)
    save_table("orders.json", orders)
    return {"order_id": order_id, "status": "confirmed", "created_at": row["created_at"]}


@app.post("/human/transfer")
def transfer_to_human(body: TransferBody) -> dict[str, Any]:
    """转人工：返回随机工号，落 transfers.json。"""
    transfers = load_table("transfers.json")
    ticket_id = _gen_id("tk", transfers)
    agent_code = f"AG-{random.randint(1000, 9999)}"
    row = {
        "id": ticket_id,
        "customer_id": body.customer_id,
        "reason": body.reason,
        "agent_code": agent_code,
        "created_at": _now(),
    }
    transfers.append(row)
    save_table("transfers.json", transfers)
    return {"ticket_id": ticket_id, "agent_code": agent_code, "message": "已为您转接人工顾问"}


def main() -> None:
    run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    asyncio.run(main())
