"""权限点目录：路由 → 所需 permission code（授权裁决的唯一依据）。

与 unify-iam-server 的 `gateway_permission` **同套 code**（doc09 §3.3 / doc10 §4.2）。
IAM 侧为权威；本文件声明 + 未来启动校验比对（IAM `gateway_permission` 预置缺失则告警）。
"""

from __future__ import annotations

# 功能权限点（命名与 IAM gateway_permission.code 一致）
AGENT_READ = "agent:read"          # 查看 Agent 定义/版本/旅程布局
AGENT_BUILD = "agent:build"        # 新建/存草稿、旅程布局编辑
AGENT_PUBLISH = "agent:publish"    # 发布
AGENT_DELETE = "agent:delete"      # 删除/卸载/回滚/删版本
SESSION_READ = "session:read"      # 会话/消息历史查看（含 SSE 事件流）
SESSION_SEND = "session:send"      # 建会话/发事件/关/删会话
CUSTOMER_MANAGE = "customer:manage"  # 客户管理
TRACE_READ = "trace:read"          # 观测链路历史
SETTINGS_READ = "settings:read"    # 平台设置查看

ALL_PERMISSIONS = frozenset(
    {
        AGENT_READ,
        AGENT_BUILD,
        AGENT_PUBLISH,
        AGENT_DELETE,
        SESSION_READ,
        SESSION_SEND,
        CUSTOMER_MANAGE,
        TRACE_READ,
        SETTINGS_READ,
    }
)