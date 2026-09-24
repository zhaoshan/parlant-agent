/** API 客户端：所有请求走 parlant-agent-server（BFF，开发期经 vite 代理 /api → 8081）。 */

import type { AgentDetail, AgentInfo, Customer, Session, SessionLedgerRow, SessionMessage } from './types'

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
  detail: (id: string) => request<AgentDetail>(`/api/agents/${id}`),
  create: (definition: unknown) =>
    request<{ agent_id: string; version: string; status: string }>('/api/agents', {
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
  list: (params: { user_id?: string; agent_id?: string; source?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.user_id) q.set('user_id', params.user_id)
    if (params.agent_id) q.set('agent_id', params.agent_id)
    if (params.source) q.set('source', params.source)
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
