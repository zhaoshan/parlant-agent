"""探活端点：/health 聚合本服务、下游 runtime、Mongo 的真实状态。"""

from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    state = request.app.state
    runtime_ok: bool | None = None
    runtime_detail: object = "未配置"
    if (client := getattr(state, "runtime_client", None)) is not None:
        try:
            runtime_detail = await client.health()
            runtime_ok = True
        except Exception as exc:  # noqa: BLE001 - 下游不可达即降级展示
            runtime_ok = False
            runtime_detail = f"{type(exc).__name__}: {exc}"

    mongo_ok: bool | None = None
    if (conn := getattr(state, "mongo", None)) is not None:
        mongo_ok = await conn.ping()

    mysql_ok: bool | None = None
    if (conn := getattr(state, "mysql", None)) is not None:
        mysql_ok = await conn.ping()

    return {
        "status": "ok" if (runtime_ok and mongo_ok and mysql_ok) else "degraded",
        "service": "parlant-agent-server",
        "runtime": {"ok": runtime_ok, "detail": runtime_detail},
        "mongo": {"ok": mongo_ok},
        "mysql": {"ok": mysql_ok},
    }