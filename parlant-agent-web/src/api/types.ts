/** 类型定义：与 parlant-agent-server 的 API 契约对应（阶段3）。 */

// ---------- Agent ----------
export interface AgentInfo {
  agent_id: string
  /** Agent 名称（定义 agent.name；旧定义可能缺失，回退 agent_id） */
  name: string | null
  published_version: string | null
  latest_version: string
  latest_status: string
  loaded: boolean
  updated_at: string | null
}

export interface AgentDetail extends AgentInfo {
  summary: {
    guidelines: number
    journeys: number
    states: number
    variables: number
    glossary: number
    canned_responses: number
    tools: number
  }
  /** 完整定义（agent-definition.json 结构，构建页草稿编辑用） */
  definition: unknown
}

/** Agent 定义里的 Context Variable（definition.variables.variables[]；引擎 id 随机生成，这里 id 只是定义层标签） */
export interface AgentVariable {
  id: string
  name: string
  /** string / number / boolean（引擎不消费 type，仅 UI 输入形态用） */
  type: string
  description?: string
  default_value?: unknown
  allowed_values?: unknown[]
}

// ---------- 会话 / 客户 ----------
export interface Customer {
  id: string
  name: string
  metadata?: Record<string, unknown>
  tags?: string[]
}

export interface Session {
  id: string
  agent_id: string
  customer_id: string
  title: string | null
  creation_utc: string
}

export type SessionSource = 'online' | 'simulate' | 'auto_sim'

export interface SessionLedgerRow {
  id: number
  user_id: string
  session_id: string
  agent_id: string
  /** 会话实际绑定的 runtime 实例 id（线上=agent_id；草稿试跑={agent_id}@draft） */
  agent_instance_id: string | null
  /** 线上=发布版本号；草稿="draft" */
  agent_version: string | null
  /** published / draft */
  agent_status: string | null
  title: string | null
  status: string
  source: SessionSource
  ended_at: string | null
  ended_reason: string | null
  created_at: string
  updated_at: string
  last_message_at: string | null
  /** 台账侧有效性：status=active 且未结束且未超时 */
  valid: boolean
  /** 无效原因：normal(正常结束) / timeout(超时结束) / null(有效) */
  invalid_reason: string | null
}

// ---------- 消息级历史（session_messages） ----------
export type MessageRole = 'customer' | 'agent'
export type MessageStatus = 'streaming' | 'completed'

export interface SessionMessage {
  id: number
  session_id: string
  request_id: string
  message_id: string
  role: MessageRole
  user_id: string | null
  user_name: string | null
  agent_id: string | null
  agent_name: string | null
  content: string
  content_type: string
  trace_id: string | null
  status: MessageStatus
  event_offset: number | null
  created_at: string
  updated_at: string
}
