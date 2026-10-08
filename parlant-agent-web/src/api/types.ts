/** 类型定义：与 parlant-agent-server 的 API 契约对应（阶段3）。 */

// ---------- Agent ----------
/** 组件统计（指南/旅程/状态/变量/术语/话术/工具）。详情与列表均返回；列表项可能缺（旧 server）。 */
export interface AgentSummary {
  guidelines: number
  journeys: number
  states: number
  variables: number
  glossary: number
  canned_responses: number
  tools: number
}

export interface AgentInfo {
  agent_id: string
  /** Agent 名称（定义 agent.name；旧定义可能缺失，回退 agent_id） */
  name: string | null
  /** Agent 业务说明（定义 agent.description；旧定义可能缺失） */
  description: string | null
  published_version: string | null
  latest_version: string
  latest_status: string
  loaded: boolean
  updated_at: string | null
  /** 组件统计（列表随附；旧 server 可能缺） */
  summary?: AgentSummary
}

export interface AgentDetail extends AgentInfo {
  summary: AgentSummary
  /** 完整定义（agent-definition.json 结构，构建页草稿编辑用） */
  definition: unknown
}

/** 版本历史条目（GET /api/agents/{id}/versions 返回；不含定义体） */
export interface AgentVersionInfo {
  version: string
  status: string
  created_by: string | null
  created_at: string | null
  updated_at: string | null
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

/** langfuse ObservationV2（server /api/traces/{id} 透传的扁平数组项） */
export interface TraceObservation {
  id: string
  traceId: string
  parentObservationId: string | null
  isRootObservation?: boolean
  /** SPAN | GENERATION | EVENT */
  type: string
  name: string
  level?: 'DEBUG' | 'DEFAULT' | 'WARNING' | 'ERROR'
  statusMessage?: string | null
  startTime: string
  endTime?: string | null
  latency?: number | null
  traceName?: string | null
  userId?: string | null
  sessionId?: string | null
  input?: unknown
  output?: unknown
  metadata?: unknown
  model?: string | null
  modelParameters?: Record<string, unknown> | null
  usageDetails?: {
    input?: number
    output?: number
    total?: number
    [k: string]: unknown
  } | null
  costDetails?: Record<string, unknown> | null
  totalCost?: number | null
  promptName?: string | null
  promptVersion?: number | null
}

// ---------- 设置页 ----------
export interface SettingsInfo {
  /** 运行时信息（runtime `/internal/info`）；runtime 不可达为 null */
  runtime: {
    service: string
    parlant_version: string
    main_llm_model: string
    embedding_model: string
  } | null
  runtime_unreachable: boolean
  langfuse: { configured: boolean; base_url: string }
}
