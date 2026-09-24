/** 模拟对话（优先实现）：会话边栏可收起 + 新对话 + SSE 流式聊天 + 消息历史（session_messages）。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { agentsApi, customersApi, sessionsApi } from '../api/client'
import type { AgentInfo, AgentVariable, SessionLedgerRow, SessionMessage } from '../api/types'
import { useApp } from '../store/app'
import { SendIcon, TraceIcon } from '../components/Icons'
import { Switch } from './build/fields'

function uuid() {
  return crypto.randomUUID()
}

// 解析 runtime SSE 事件（事件 DTO：source/kind 在顶层，data 内是 message/status）
interface SseEvent {
  id?: string
  source?: string
  kind?: string
  offset?: number
  trace_id?: string
  data?: { message?: string; chunks?: (string | null)[]; status?: string; participant?: { id?: string; display_name?: string } }
}

export default function Simulate() {
  const navigate = useNavigate()
  const { currentAgent, currentUser } = useApp()

  const [sessions, setSessions] = useState<SessionLedgerRow[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<SessionMessage[]>([])
  const [processing, setProcessing] = useState(false)
  const [deadSession, setDeadSession] = useState(false)
  const [invalidReason, setInvalidReason] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [sessCollapsed, setSessCollapsed] = useState(false)
  const [railCollapsed, setRailCollapsed] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [kw, setKw] = useState('')
  const esRef = useRef<EventSource | null>(null)
  const offsetRef = useRef(0)
  const threadRef = useRef<HTMLDivElement>(null)

  const loadSessions = useCallback(() => {
    if (!currentAgent) {
      setSessions([])
      return
    }
    // 只查当前 Agent 的模拟对话会话；默认不带用户过滤
    sessionsApi
      .list({ agent_id: currentAgent.agent_id, source: 'simulate' })
      .then((r) => setSessions(r.sessions))
      .catch(() => {})
  }, [currentAgent])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight })
  }, [messages])

  const closeSse = () => {
    esRef.current?.close()
    esRef.current = null
  }

  const openSession = useCallback(
    (sessionId: string, valid: boolean, reason: string | null) => {
      closeSse()
      setActiveId(sessionId)
      setMessages([])
      setProcessing(false)
      // 有效性由台账侧判定（status/ended/超时），不依赖 runtime 探活
      setDeadSession(!valid)
      setInvalidReason(reason)
      offsetRef.current = 0
      // 先拉消息历史（session_messages），再从最后 offset 续 SSE
      sessionsApi
        .messages(sessionId)
        .then((r) => {
          const ms = r.messages
          setMessages(ms)
          const maxOff = Math.max(0, ...ms.map((m) => m.event_offset ?? 0))
          offsetRef.current = maxOff
          startSse(sessionId, maxOff)
        })
        .catch(() => {})
    },
    [],
  )

  const removeSession = async (sessionId: string) => {
    try {
      await sessionsApi.remove(sessionId)
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
      if (activeId === sessionId) {
        closeSse()
        setActiveId(null)
        setMessages([])
      }
    } catch (err) {
      console.error('delete failed', err)
    }
  }

  const startSse = (sessionId: string, minOffset: number) => {
    const es = new EventSource(sessionsApi.eventsUrl(sessionId, minOffset))
    es.onmessage = (e) => {
      let ev: SseEvent
      try {
        ev = JSON.parse(e.data)
      } catch {
        return
      }
      const off = ev.offset ?? 0
      if (off >= offsetRef.current) offsetRef.current = off + 1

      if (ev.kind === 'status') {
        const s = ev.data?.status
        setProcessing(s === 'processing' || s === 'typing' || s === 'acknowledged')
        return
      }
      if (ev.kind !== 'message') return
      const src = ev.source
      const text = ev.data?.message ?? ''
      if (src === 'customer') {
        setMessages((prev) =>
          prev.some((m) => m.message_id === ev.id) ? prev : [...prev, msg(ev.id, 'customer', text, null, off, currentUser.user_name)],
        )
      } else if (src === 'ai_agent') {
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.message_id === ev.id)
          if (idx >= 0) {
            const next = [...prev]
            next[idx] = { ...next[idx], content: text || next[idx].content, trace_id: ev.trace_id ?? next[idx].trace_id, status: 'completed' }
            return next
          }
          return [...prev, msg(ev.id, 'agent', text, ev.trace_id ?? null, off, null)]
        })
        setProcessing(false)
      }
    }
    es.onerror = () => {
      // EventSource 自动重连；保持连接即可
    }
    esRef.current = es
  }

  const send = async () => {
    const text = input.trim()
    if (!text || !activeId || processing) return
    setInput('')
    const requestId = uuid()
    const tempId = uuid()
    // 乐观插入客户消息（临时 id；POST 返回真实事件 id 后替换，避免与 SSE 回显重复）
    setMessages((prev) => [...prev, msg(tempId, 'customer', text, null, offsetRef.current, currentUser.user_name)])
    try {
      const event = await sessionsApi.postEvent(
        activeId,
        { kind: 'message', source: 'customer', message: text },
        { request_id: requestId, user_id: currentUser.user_id, user_name: currentUser.user_name },
      )
      if (event && typeof (event as { id?: string }).id === 'string') {
        const realId = (event as { id: string }).id
        setMessages((prev) => prev.map((m) => (m.message_id === tempId ? { ...m, message_id: realId } : m)))
      }
    } catch (err) {
      console.error('send failed', err)
    }
  }

  const shownSessions = sessions.filter(
    (s) => !kw || s.title?.includes(kw) || s.session_id.includes(kw),
  )

  return (
    <div className="flex h-screen min-w-0 flex-col">
      {/* topbar */}
      <div className="flex h-[52px] flex-none items-center gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-3 pl-4">
        <button
          className="grid h-8 w-8 place-items-center rounded-md text-[var(--muted)] hover:bg-[#EDF0F4] hover:text-[var(--ink)]"
          title="收起/展开会话列表"
          onClick={() => setSessCollapsed((v) => !v)}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M3 9h18M9 21V9" />
          </svg>
        </button>
        <div className="flex items-center gap-2.5">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--primary-weak)] text-[13px] font-semibold text-[var(--primary)]">
            {currentAgent?.agent_id?.slice(0, 1).toUpperCase() ?? '?'}
          </div>
          <div>
            <div className="flex items-center gap-1.5 text-[13px] font-semibold">
              {currentAgent?.agent_id ?? '未选择 Agent'}
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)]" />
            </div>
            <div className="mono text-[11px] text-[var(--muted)]">{currentAgent?.agent_id}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 border-l border-[var(--line)] pl-4 text-[12.5px] text-[var(--ink-2)]">
          会话 · <b className="text-[var(--ink)]">{activeId ? sessions.find((s) => s.session_id === activeId)?.title ?? activeId.slice(0, 8) : '—'}</b>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button className="trace-btn" onClick={() => navigate('/obs')}>
            <TraceIcon size={13} /> langfuse 链路
          </button>
          <button
            className="inline-flex h-7.5 items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-[12px] font-medium text-[var(--ink-2)] hover:bg-[#F1F5F9]"
            onClick={() => setDialogOpen(true)}
          >
            新对话
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* 会话边栏（可收起） */}
        <aside
          className={`flex w-[268px] flex-none flex-col border-r border-[var(--line)] bg-[var(--surface)] transition-[margin-left] duration-200 ${
            sessCollapsed ? '-ml-[268px]' : ''
          }`}
        >
          <div className="flex items-center gap-2 border-b border-[var(--line)] px-3.5 py-3">
            <span className="flex-1 text-[13px] font-semibold">会话列表</span>
            <button
              className="inline-flex h-6.5 items-center rounded-md bg-[var(--primary-weak)] px-2 text-[11.5px] font-medium text-[var(--primary)] hover:bg-[#E0E7FF]"
              onClick={() => setDialogOpen(true)}
            >
              ＋ 新对话
            </button>
          </div>
          <div className="mx-3.5 mt-2.5 mb-2 flex h-[30px] items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--bg)] px-2 text-[var(--muted)]">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              className="flex-1 border-0 bg-transparent text-[12px] text-[var(--ink)] outline-none"
              placeholder="搜索会话…"
              value={kw}
              onChange={(e) => setKw(e.target.value)}
            />
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {shownSessions.map((s) => (
              <div
                key={s.session_id}
                className={`group mb-0.5 block w-full cursor-pointer rounded-lg border p-2.5 text-left font-sans ${
                  activeId === s.session_id
                    ? 'border-[var(--primary-line)] bg-[var(--primary-weak)]'
                    : 'border-transparent hover:bg-[var(--bg)]'
                }`}
                onClick={() => openSession(s.session_id, s.valid, s.invalid_reason)}
              >
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-[12.5px] font-semibold text-[var(--ink)]">
                    <span
                      className={`mr-1 inline-block h-1.5 w-1.5 flex-none rounded-full ${
                        s.valid ? 'bg-[var(--success)]' : 'bg-[var(--muted)]'
                      }`}
                    />
                    {s.title ?? '未命名会话'}
                  </span>
                  {s.agent_status === 'draft' && (
                    <span className="flex-none rounded bg-[var(--warning-weak)] px-1 py-0.5 text-[9.5px] font-medium text-[var(--warning)]">草稿</span>
                  )}
                  <span className="ml-auto text-[10.5px] text-[var(--muted)]">
                    {s.valid ? '进行中' : s.invalid_reason === 'timeout' ? '超时' : '已结束'}
                  </span>
                  <button
                    className="grid h-5 w-5 flex-none cursor-pointer place-items-center rounded text-[var(--muted)] opacity-0 transition group-hover:opacity-100 hover:bg-[#FEF2F2] hover:text-[var(--danger)]"
                    title="删除会话"
                    onClick={(e) => {
                      e.stopPropagation()
                      removeSession(s.session_id)
                    }}
                  >
                    ✕
                  </button>
                </span>
                <span className="mono mt-0.5 block text-[10px] text-[var(--muted)]">{s.session_id}</span>
              </div>
            ))}
            {!shownSessions.length && (
              <div className="px-4 py-8 text-center text-[12px] text-[var(--muted)]">暂无会话，点「新对话」开始</div>
            )}
          </div>
        </aside>

        {/* 对话主区 */}
        <section className="flex min-w-0 flex-1 flex-col bg-[var(--bg)]">
          {deadSession && (
            <div className="mx-auto mt-3 flex w-[min(720px,calc(100%-2rem))] items-center gap-2 rounded-lg border border-[#E7C08B] bg-[var(--warning-weak)] px-3.5 py-2.5 text-[12px] text-[var(--warning)]">
              <span className="h-1.5 w-1.5 flex-none rounded-full bg-[var(--warning)]" />
              {invalidReason === 'timeout'
                ? '该会话已超时结束（超过 1 天未活跃，自动失效）：历史消息可查看，继续提问请新建会话。'
                : '该会话已结束（正常结束）：历史消息可查看，继续提问请新建会话。'}
            </div>
          )}
          <div ref={threadRef} className="flex-1 overflow-y-auto px-8 pb-3 pt-6">
            <div className="mx-auto flex max-w-[720px] flex-col gap-4">
              {messages.map((m) => (
                <div key={m.message_id} className={`flex flex-col gap-1.5 ${m.role === 'customer' ? 'items-start' : 'items-end'}`}>
                  <div className={`flex items-center gap-1.5 text-[11.5px] text-[var(--muted)] ${m.role === 'agent' ? 'flex-row-reverse' : ''}`}>
                    {m.role === 'customer' ? m.user_name ?? '用户' : m.agent_name ?? 'Agent'}
                  </div>
                  <div
                    className={`max-w-[72%] rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                      m.role === 'customer'
                        ? 'rounded-tl border border-[var(--line)] bg-[var(--surface)]'
                        : 'rounded-tr border border-[var(--primary-line)] bg-[var(--primary-weak)]'
                    }`}
                  >
                    {m.content}
                    {m.status === 'streaming' && <span className="ml-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--primary)] align-middle" />}
                  </div>
                  {m.role === 'agent' && (
                    <div className="flex items-center gap-2">
                      {m.trace_id && (
                        <a
                          className="inline-flex cursor-pointer items-center gap-1 text-[11px] text-[var(--primary)] hover:underline"
                          onClick={() => alert(`langfuse trace: ${m.trace_id}`)}
                        >
                          <TraceIcon size={12} />
                          查看链路
                          <span className="mono text-[10px] text-[var(--muted)]">{m.trace_id.slice(0, 8)}…</span>
                        </a>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {processing && (
                <div className="flex items-center gap-2 self-end text-[12px] text-[var(--primary)]">
                  正在处理
                  <span className="flex gap-0.5">
                    {[0, 1, 2].map((i) => (
                      <i key={i} className="h-1.5 w-1.5 animate-bounce rounded-full bg-[var(--primary)]" style={{ animationDelay: `${i * 0.15}s` }} />
                    ))}
                  </span>
                </div>
              )}
              {!activeId && (
                <div className="mx-auto py-16 text-center text-[13px] text-[var(--muted)]">
                  从左侧选择一个会话，或
                  <button className="ml-1 cursor-pointer font-medium text-[var(--primary)]" onClick={() => setDialogOpen(true)}>
                    开始新对话
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* composer */}
          <div className="flex-none border-t border-[var(--line)] bg-[var(--surface)] px-8 pb-4 pt-3.5">
            <div className="mx-auto max-w-[720px]">
              <div className="flex items-center rounded-xl border border-[var(--line-strong)] bg-white px-3.5 py-2.5 transition focus-within:border-[var(--primary)] focus-within:shadow-[0_0_0_3px_var(--primary-weak)]">
                <textarea
                  className="max-h-[140px] min-h-[22px] flex-1 resize-none border-0 bg-transparent text-[13px] leading-relaxed text-[var(--ink)] outline-none"
                  rows={1}
                  placeholder="输入消息…（Enter 发送，Shift+Enter 换行）"
                  value={input}
                  disabled={!activeId || deadSession}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      send()
                    }
                  }}
                />
                <button
                  className="grid h-8 w-8 flex-none cursor-pointer place-items-center rounded-lg bg-[var(--primary)] text-white disabled:cursor-not-allowed disabled:bg-[#A5B4FC]"
                  disabled={!activeId || deadSession || !input.trim() || processing}
                  onClick={send}
                >
                  <SendIcon size={15} />
                </button>
              </div>
              <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--muted)]">
                <span>经由 server SSE 透传 · 消息历史落 session_messages</span>
                <span className="mono ml-auto text-[10.5px]">GET /api/sessions/{'{id}'}/events</span>
              </div>
            </div>
          </div>
        </section>

        {/* 执行详情（可折叠） */}
        <button
          className="absolute right-0 top-[60px] z-5 grid h-6 w-6 cursor-pointer place-items-center rounded-l-md border border-r-0 border-[var(--line)] bg-[var(--surface)] text-[var(--muted)]"
          onClick={() => setRailCollapsed((v) => !v)}
        >
          {railCollapsed ? '❮' : '❯'}
        </button>
        <aside
          className={`w-[300px] flex-none overflow-y-auto border-l border-[var(--line)] bg-[var(--surface)] p-4 transition-[margin-right] duration-200 ${
            railCollapsed ? '-mr-[300px]' : ''
          }`}
        >
          <div className="mb-5">
            <h4 className="mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-[var(--muted)]">会话状态</h4>
            <div
              className={`flex items-center gap-2 rounded-lg px-3 py-2.5 text-[12px] font-medium ${
                processing ? 'bg-[var(--warning-weak)] text-[var(--warning)]' : 'bg-[var(--success-weak)] text-[var(--success)]'
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${processing ? 'animate-pulse bg-[var(--warning)]' : 'bg-[var(--success)]'}`} />
              {processing ? 'processing · 引擎处理中' : 'ready · 就绪'}
            </div>
          </div>

          <div className="mb-5">
            <h4 className="mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold tracking-wider text-[var(--muted)]">最近链路</h4>
            <div className="rounded-lg border border-dashed border-[var(--primary-line)] bg-[var(--primary-weak)] p-3 text-[11.5px] text-[var(--primary)]">
              {messages.findLast((m) => m.role === 'agent')?.trace_id ? (
                <>
                  最近 Agent 回复 trace_id
                  <span className="mono mt-1.5 block break-all text-[11px]">
                    {messages.findLast((m) => m.role === 'agent')?.trace_id}
                  </span>
                  <span className="mt-1 block text-[11px] opacity-80">
                    process → guideline_matcher → tool_caller → message_generation
                  </span>
                </>
              ) : (
                '暂无链路（发送消息后出现）'
              )}
            </div>
          </div>
        </aside>
      </div>

      {dialogOpen && (
        <NewConversationDialog
          agents={[currentAgent].filter(Boolean) as AgentInfo[]}
          userId={currentUser.user_id}
          userName={currentUser.user_name}
          onClose={() => setDialogOpen(false)}
          onCreated={(sessionId) => {
            setDialogOpen(false)
            loadSessions()
            openSession(sessionId, true, null)
          }}
        />
      )}
    </div>
  )
}

function msg(
  id: string | undefined,
  role: 'customer' | 'agent',
  content: string,
  traceId: string | null,
  offset: number,
  userName: string | null,
): SessionMessage {
  return {
    id: -1,
    session_id: '',
    request_id: '',
    message_id: id ?? uuid(),
    role,
    user_id: null,
    user_name: userName,
    agent_id: null,
    agent_name: role === 'agent' ? 'Agent' : null,
    content,
    content_type: 'text',
    trace_id: traceId,
    status: 'completed',
    event_offset: offset,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
}

// ---------- 新对话对话框（选 Agent + 客户身份 + 变量覆盖） ----------
interface OverrideEntry {
  active: boolean
  value: unknown
}

function NewConversationDialog(props: {
  agents: AgentInfo[]
  userId: string
  userName: string
  onClose: () => void
  onCreated: (sessionId: string) => void
}) {
  const { agents, userId, onClose, onCreated } = props
  const [agentId, setAgentId] = useState(agents[0]?.agent_id ?? '')
  const [mode, setMode] = useState<'draft' | 'published'>('draft')
  const [useGuest, setUseGuest] = useState(false)
  const [customerId, setCustomerId] = useState('')
  const [customerName, setCustomerName] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  // 变量覆盖：定义元数据（name/type/默认值，来自 agent 定义）+ 用户逐变量覆盖态
  const [varMeta, setVarMeta] = useState<AgentVariable[]>([])
  const [varLoading, setVarLoading] = useState(false)
  const [overrides, setOverrides] = useState<Record<string, OverrideEntry>>({})

  // 切换 Agent 时拉取该 agent 定义里的变量清单（name→type/default 供输入控件）
  useEffect(() => {
    let cancelled = false
    if (!agentId) {
      setVarMeta([])
      return
    }
    setVarLoading(true)
    agentsApi
      .detail(agentId)
      .then((d) => {
        if (cancelled) return
        const def = d.definition as { variables?: { variables?: AgentVariable[] } } | null
        setVarMeta(def?.variables?.variables ?? [])
        setOverrides({})
      })
      .catch(() => {
        if (!cancelled) setVarMeta([])
      })
      .finally(() => {
        if (!cancelled) setVarLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [agentId])

  const setVarActive = (name: string, v: AgentVariable, active: boolean) => {
    setOverrides((prev) => {
      if (!active) {
        const next = { ...prev }
        delete next[name]
        return next
      }
      const cur = prev[name]
      // 首次开启：默认带出定义里的默认值（可改）；重复开启保留已输入值
      return { ...prev, [name]: { active: true, value: cur ? cur.value : v.default_value } }
    })
  }
  const setVarValue = (name: string, value: unknown) => {
    setOverrides((prev) => ({ ...prev, [name]: { active: true, value } }))
  }

  const start = async () => {
    if (!agentId || busy) return
    setBusy(true)
    try {
      let cid = 'guest'
      if (!useGuest) {
        const id = customerId || `cust_${Date.now()}`
        await customersApi.create({ name: customerName || '客户', id })
        cid = id
      }
      // 汇总"已开启且值非空"的变量覆盖（按变量名，runtime 按名解析到引擎 id）
      const vars: Record<string, unknown> = {}
      for (const v of varMeta) {
        const o = overrides[v.name]
        if (!o?.active) continue
        if (o.value === undefined || o.value === null) continue
        if (typeof o.value === 'string' && o.value.trim() === '') continue
        vars[v.name] = o.value
      }
      const res = await sessionsApi.create({
        agent_id: agentId,
        customer_id: cid,
        user_id: userId,
        title: title || undefined,
        source: 'simulate',
        mode,
        variables: Object.keys(vars).length ? vars : undefined,
      })
      const vo = res.variable_overrides
      if (vo?.missing?.length) {
        alert(`部分变量未覆盖（当前 Agent 无此变量名）：${vo.missing.join('、')}`)
      } else if (vo?.error) {
        alert(`变量覆盖失败（会话已创建）：${vo.error}`)
      }
      onCreated(res.session.id)
    } catch (err) {
      alert(`创建会话失败：${err}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-60 grid place-items-center bg-[rgba(15,23,42,.45)]" onClick={onClose}>
      <div className="w-[560px] max-h-[82vh] overflow-auto rounded-xl bg-[var(--surface)] p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-[15px] font-semibold">开始新对话</h3>
            <p className="mt-1 text-[12px] text-[var(--muted)]">选择 Agent 与客户身份，可覆盖 journey 配置的变量（POST /api/customers → POST /api/sessions）</p>
          </div>
          <button className="cursor-pointer rounded-md p-1 text-[var(--muted)] hover:bg-[#EDF0F4]" onClick={onClose}>✕</button>
        </div>

        <div className="mt-3 text-[12.5px] font-semibold text-[var(--ink-2)]">1 · 选择 Agent</div>
        <div className="mt-2 flex flex-col gap-2">
          {agents.map((a) => (
            <div
              key={a.agent_id}
              className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 ${
                agentId === a.agent_id ? 'border-[var(--primary)] shadow-[0_0_0_3px_var(--primary-weak)]' : 'border-[var(--line)]'
              }`}
              onClick={() => setAgentId(a.agent_id)}
            >
              <span className={`h-4 w-4 flex-none rounded-full border-[1.5px] ${agentId === a.agent_id ? 'border-[4.5px] border-[var(--primary)]' : 'border-[var(--line-strong)]'}`} />
              <div>
                <div className="text-[13px] font-semibold">{a.agent_id}</div>
                <div className="mono text-[10.5px] text-[var(--muted)]">{a.agent_id}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 text-[12.5px] font-semibold text-[var(--ink-2)]">试跑目标（不影响线上）</div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          {(
            [
              ['draft', '当前草稿', '含未发布变更，默认'],
              ['published', '线上版本', '已发布行为'],
            ] as const
          ).map(([v, label, hint]) => (
            <div
              key={v}
              className={`flex cursor-pointer items-center gap-2 rounded-lg border p-2.5 ${mode === v ? 'border-[var(--primary)] shadow-[0_0_0_3px_var(--primary-weak)]' : 'border-[var(--line)]'}`}
              onClick={() => setMode(v)}
            >
              <span className={`h-3.5 w-3.5 flex-none rounded-full border-[1.5px] ${mode === v ? 'border-[4px] border-[var(--primary)]' : 'border-[var(--line-strong)]'}`} />
              <div>
                <div className="text-[12.5px] font-medium">{label}</div>
                <div className="text-[10.5px] text-[var(--muted)]">{hint}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 text-[12.5px] font-semibold text-[var(--ink-2)]">2 · 客户身份</div>
        <div className="mt-2 flex flex-col gap-2.5">
          <label className="flex items-center gap-2 text-[12px]">
            <input type="checkbox" checked={useGuest} onChange={(e) => setUseGuest(e.target.checked)} />
            使用内置 guest 客户快速冒烟
          </label>
          {!useGuest && (
            <div className="grid grid-cols-2 items-start gap-2.5">
              <Field label="客户 ID" mono value={customerId} onChange={setCustomerId} placeholder="唯一标识，缺省自动生成" />
              <Field label="姓名" value={customerName} onChange={setCustomerName} placeholder="客户称呼" />
            </div>
          )}
          <Field label="会话标题" value={title} onChange={setTitle} placeholder="如：提前结清咨询" />
        </div>

        {/* 3 · 变量覆盖（可选） */}
        <div className="mt-4 text-[12.5px] font-semibold text-[var(--ink-2)]">3 · 变量覆盖（可选）</div>
        <p className="mt-0.5 text-[10.5px] text-[var(--muted)]">
          按客户维度覆盖 journey 配置的变量默认值，仅本会话客户生效（key=customer.id 优先级最高）
        </p>
        <div className="mt-2 grid grid-cols-2 items-start gap-2">
          {varLoading ? (
            <div className="col-span-2 py-3 text-center text-[11.5px] text-[var(--muted)]">加载变量中…</div>
          ) : varMeta.length ? (
            varMeta.map((v) => (
              <VarOverrideRow
                key={v.name}
                v={v}
                entry={overrides[v.name]}
                onToggle={(active) => setVarActive(v.name, v, active)}
                onValue={(value) => setVarValue(v.name, value)}
              />
            ))
          ) : (
            <div className="col-span-2 py-3 text-center text-[11.5px] text-[var(--muted)]">该 Agent 没有配置 Context Variable</div>
          )}
        </div>

        <div className="mt-4 flex items-center gap-2.5 border-t border-[var(--line)] pt-4">
          <button className="inline-flex h-8 items-center rounded-md border border-[var(--line-strong)] px-3.5 text-[12.5px] text-[var(--ink-2)]" onClick={onClose}>
            取消
          </button>
          <div className="flex-1" />
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[var(--primary)] px-4 text-[12.5px] font-medium text-white hover:bg-[#4338CA] disabled:opacity-60"
            disabled={!agentId || busy}
            onClick={start}
          >
            {busy ? '创建中…' : '开始对话'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** 单条变量覆盖行：勾选"覆盖"后按类型出控件（boolean→Switch，allowed_values→下拉，number→数字，string→多行文本）。 */
function VarOverrideRow(props: {
  v: AgentVariable
  entry?: OverrideEntry
  onToggle: (active: boolean) => void
  onValue: (value: unknown) => void
}) {
  const { v, entry, onToggle, onValue } = props
  const active = !!entry?.active
  const value = entry?.value
  const allowed = Array.isArray(v.allowed_values) && v.allowed_values.length > 0 ? v.allowed_values : null

  const fmt = (x: unknown) => {
    if (x === undefined || x === null) return ''
    return typeof x === 'object' ? JSON.stringify(x) : String(x)
  }
  // 控件占满行宽（两栏布局下尽量宽）
  const inputCls =
    'h-[34px] w-full rounded-md border border-[var(--line-strong)] bg-white px-2.5 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)]'
  const textareaCls =
    'w-full resize-y rounded-md border border-[var(--line-strong)] bg-white px-2.5 py-2 text-[12.5px] leading-relaxed text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)]'

  let control: React.ReactNode = null
  if (v.type === 'boolean') {
    control = (
      <div className="flex items-center gap-2">
        <Switch checked={value === true} onChange={(b) => onValue(b)} />
        <span className="text-[11.5px] text-[var(--muted)]">{value === true ? 'true' : 'false'}</span>
      </div>
    )
  } else if (allowed) {
    control = (
      <select className={inputCls} value={fmt(value)} onChange={(e) => onValue(e.target.value)}>
        {allowed.map((a) => (
          <option key={fmt(a)} value={fmt(a)}>
            {fmt(a)}
          </option>
        ))}
      </select>
    )
  } else if (v.type === 'number' || v.type === 'integer') {
    control = (
      <input
        type="number"
        className={inputCls}
        value={value === undefined || value === null ? '' : String(value)}
        placeholder={fmt(v.default_value) || '0'}
        onChange={(e) => onValue(e.target.value === '' ? undefined : Number(e.target.value))}
      />
    )
  } else {
    control = (
      <textarea
        rows={3}
        className={textareaCls}
        value={value === undefined || value === null ? '' : String(value)}
        placeholder={fmt(v.default_value) || '留空不覆盖'}
        onChange={(e) => onValue(e.target.value)}
      />
    )
  }

  return (
    <div className={`rounded-lg border bg-[var(--bg)] p-2.5 ${active ? 'border-[var(--primary-weak)]' : 'border-[var(--line)]'}`}>
      <div className="flex items-center gap-2">
        <button
          className={`grid h-4 w-4 flex-none cursor-pointer place-items-center rounded border text-white ${active ? 'border-[var(--primary)] bg-[var(--primary)]' : 'border-[var(--line-strong)] bg-white'}`}
          onClick={() => onToggle(!active)}
          aria-pressed={active}
          aria-label={`覆盖变量 ${v.name}`}
        >
          {active && <span className="text-[10px] leading-none">✓</span>}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="mono text-[12px] font-semibold text-[var(--ink)]">{v.name}</span>
            <span className="rounded bg-[#EDF0F4] px-1.5 py-0.5 text-[9.5px] text-[var(--muted)]">{v.type}</span>
          </div>
          {v.description ? <div className="line-clamp-2 text-[10.5px] text-[var(--muted)]">{v.description}</div> : null}
        </div>
      </div>
      {active && <div className="mt-2 pl-6">{control}</div>}
    </div>
  )
}

function Field(props: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; mono?: boolean }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12px] font-medium text-[var(--ink-2)]">{props.label}</span>
      <input
        className={`h-[34px] rounded-md border border-[var(--line-strong)] px-2.5 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)] ${
          props.mono ? 'mono' : ''
        }`}
        value={props.value}
        placeholder={props.placeholder}
        onChange={(e) => props.onChange(e.target.value)}
      />
    </label>
  )
}
