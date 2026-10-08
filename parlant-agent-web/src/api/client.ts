/** API 客户端：所有请求走 parlant-agent-server（BFF，开发期经 vite 代理 /api → 8081）。 */

import type { AgentDetail, AgentInfo, AgentVersionInfo, Customer, Session, SessionLedgerRow, SessionMessage, SettingsInfo, TraceObservation } from './types'

const BASE = ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init)
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`
    try {
      const body = await resp.json()
      if (body?.detail) detail = String(body.detail).slice(0, 300)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

// ---------- Agent ----------
export const agentsApi = {
  list: () => request<{ agents: AgentInfo[] }>('/api/agents').then((r) => r.agents),
  detail: (id: string, version?: string) => {
    const q = version ? `?version=${encodeURIComponent(version)}` : ''
    return request<AgentDetail>(`/api/agents/${id}${q}`)
  },
  /** 版本历史（不含定义体，列表用） */
  versions: (id: string) =>
    request<{ agent_id: string; versions: AgentVersionInfo[] }>(`/api/agents/${id}/versions`).then((r) => r.versions),
  create: (definition: unknown, strict: boolean = false) =>
    request<{ agent_id: string; version: string; status: string }>(`/api/agents${strict ? '?strict=1' : ''}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(definition),
    }),
  publish: (id: string, version?: string) =>
    request(`/api/agents/${id}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version: version ?? null }),
    }),
  rollback: (id: string, version: string) =>
    request(`/api/agents/${id}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    }),
  /** 停用：仅卸载 runtime 引擎实体，版本保留 */
  unload: (id: string) =>
    request<{ agent_id: string; unloaded: boolean }>(`/api/agents/${id}`, { method: 'DELETE' }),
  /** 逻辑删除：卸载运行时 + 定义层打墓碑，定义保留在 Mongo（可恢复），列表不再展示 */
  deleteAgent: (id: string) =>
    request<{ agent_id: string; deleted: boolean; soft: boolean; versions_marked: number }>(
      `/api/agents/${id}/delete`,
      { method: 'DELETE' },
    ),
}

// ---------- 设置 ----------
export const settingsApi = {
  /** 平台级设置：runtime 模型/版本 + langfuse 接入状态 */
  get: () => request<SettingsInfo>('/api/settings'),
}

// ---------- 客户 ----------
export const customersApi = {
  list: () => request<{ customers: Customer[] }>('/api/customers').then((r) => r.customers),
  create: (body: { name: string; id?: string; metadata?: Record<string, unknown>; tags?: string[] }) =>
    request<Customer>('/api/customers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
}

// ---------- 会话 ----------
export const sessionsApi = {
  create: (body: { agent_id: string; customer_id: string; user_id?: string; title?: string; source?: string; mode?: string; variables?: Record<string, unknown> }) =>
    request<{ session: Session; ledger: SessionLedgerRow | null; variable_overrides?: { applied?: Record<string, string>; missing?: string[]; error?: string } }>(
      '/api/sessions',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      },
    ),
  detail: (id: string) => request<{ session: Session; ledger: SessionLedgerRow | null }>(`/api/sessions/${id}`),
  /** 会话列表：按 agent/来源/用户过滤（条件可空，默认查全量） */
  list: (params: { user_id?: string; agent_id?: string; source?: string; session_id?: string; status?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.user_id) q.set('user_id', params.user_id)
    if (params.agent_id) q.set('agent_id', params.agent_id)
    if (params.source) q.set('source', params.source)
    if (params.session_id) q.set('session_id', params.session_id)
    if (params.status) q.set('status', params.status)
    if (params.limit !== undefined) q.set('limit', String(params.limit))
    if (params.offset !== undefined) q.set('offset', String(params.offset))
    const qs = q.toString()
    return request<{ sessions: SessionLedgerRow[]; count: number }>(`/api/sessions${qs ? `?${qs}` : ''}`)
  },
  /** 主动关闭会话（正常结束） */
  close: (sessionId: string) =>
    request<{ closed: boolean; session_id: string; reason: string }>(`/api/sessions/${sessionId}/close`, { method: 'POST' }),
  /** 删除会话（台账 + 消息历史） */
  remove: (sessionId: string) =>
    request<{ deleted: boolean; session_id: string }>(`/api/sessions/${sessionId}`, { method: 'DELETE' }),
  /** 发消息；request_id 由前端生成（uuid），用户提问与 Agent 多条回复共用 */
  postEvent: (sessionId: string, payload: Record<string, unknown>, ctx: { request_id?: string; user_id?: string; user_name?: string }) => {
    const q = new URLSearchParams()
    if (ctx.request_id) q.set('request_id', ctx.request_id)
    if (ctx.user_id) q.set('user_id', ctx.user_id)
    if (ctx.user_name) q.set('user_name', ctx.user_name)
    const qs = q.toString()
    return request(`/api/sessions/${sessionId}/events${qs ? `?${qs}` : ''}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  /** 消息级历史（session_messages） */
  messages: (sessionId: string, requestId?: string) =>
    request<{ session_id: string; messages: SessionMessage[]; count: number }>(
      `/api/sessions/${sessionId}/messages${requestId ? `?request_id=${encodeURIComponent(requestId)}` : ''}`,
    ),
  /** SSE 事件流（EventSource 消费，min_offset 续传） */
  eventsUrl: (sessionId: string, minOffset = 0) => `/api/sessions/${sessionId}/events?min_offset=${minOffset}`,
}

// ---------- 旅程流程图布局（连线挂载点 + 节点坐标，纯 UI，独立于定义层） ----------
export type AnchorSide = 'top' | 'right' | 'bottom' | 'left'
export interface EdgeAnchors {
  /** 源端挂载点；缺省 = 自动（按几何关系） */
  from_anchor?: AnchorSide
  /** 目标端挂载点；缺省 = 自动 */
  to_anchor?: AnchorSide
}
export interface NodePos {
  /** 节点方块左上角在画布中的坐标 */
  x: number
  y: number
}
export interface JourneyLayout {
  agent_id: string
  journey_id: string
  edges: Record<string, EdgeAnchors>
  /** 用户拖拽落点（partial 覆盖自动布局）；旧文档可能无此字段 */
  nodes?: Record<string, NodePos>
}
export const journeyLayoutsApi = {
  get: (agentId: string, journeyId: string) =>
    request<JourneyLayout>(`/api/agents/${agentId}/journeys/${encodeURIComponent(journeyId)}/layout`),
  save: (agentId: string, journeyId: string, layout: { edges: Record<string, EdgeAnchors>; nodes: Record<string, NodePos> }) =>
    request<JourneyLayout>(`/api/agents/${agentId}/journeys/${encodeURIComponent(journeyId)}/layout`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(layout),
    }),
}

// ---------- 链路历史（langfuse，经 server 代理取数） ----------
export const tracesApi = {
  /** 拉取一个 trace 的全部 observation（扁平数组，前端组树） */
  get: (traceId: string) =>
    request<{ trace_id: string; observations: TraceObservation[] }>(`/api/traces/${encodeURIComponent(traceId)}`),
}
