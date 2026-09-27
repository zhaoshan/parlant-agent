/** 追踪与观测：Agent 头部（同 Agent 构建）+ 顶部 tabs（会话记录 / 链路历史）。
 *  会话记录 = 主从布局：可收起会话边栏（贴左）+ 右侧只读对话面板（一轮一轮展示）。
 *  筛选：来源渠道 / 有效性状态 / 会话 id 模糊；无标题会话由 server 用首条提问自动作标题。
 *  链路历史：按 traceId 查询 langfuse 执行链路（经 server /api/traces 代理取数），
 *  左侧整棵树（span/generation/event）+ 右侧节点详情；会话记录消息旁「查看链路」深链进入。 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { sessionsApi, tracesApi } from '../api/client'
import type { SessionLedgerRow, SessionMessage, TraceObservation } from '../api/types'
import { TraceIcon } from '../components/Icons'
import { useApp } from '../store/app'
import { agentInitial } from '../utils/agent'

const PAGE_SIZE = 30
const SOURCE_LABEL: Record<string, string> = { online: '线上问答', simulate: '模拟对话', auto_sim: '自动仿真' }

/** 把扁平消息流按「轮」分组：客户提问开启一轮，其后 Agent 回复并入该轮。 */
function groupRounds(msgs: SessionMessage[]): { requestId: string | null; messages: SessionMessage[] }[] {
  const rounds: { requestId: string | null; messages: SessionMessage[] }[] = []
  for (const m of msgs) {
    if (m.role === 'customer') rounds.push({ requestId: m.request_id, messages: [m] })
    else if (rounds.length) rounds[rounds.length - 1].messages.push(m)
    else rounds.push({ requestId: m.request_id, messages: [m] })
  }
  return rounds
}

export default function Observability() {
  const navigate = useNavigate()
  const { currentAgent } = useApp()
  const [search] = useSearchParams()
  const traceId = search.get('trace')
  const traceSession = search.get('session')
  // 深链带 trace → 链路历史 tab；否则会话记录（主从）
  const [tab, setTab] = useState<'sessions' | 'traces'>(traceId ? 'traces' : 'sessions')

  // ---------- 会话列表（筛选 + 分页） ----------
  const [rows, setRows] = useState<SessionLedgerRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [source, setSource] = useState('')
  const [status, setStatus] = useState('')
  const [sid, setSid] = useState('')
  const [sidInput, setSidInput] = useState('')

  // ---------- 主从 ----------
  const [active, setActive] = useState<SessionLedgerRow | null>(null)
  const [msgs, setMsgs] = useState<SessionMessage[]>([])
  const [msgsLoading, setMsgsLoading] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  // 深链带 trace：切到链路历史 tab
  useEffect(() => {
    if (traceId) setTab('traces')
  }, [traceId])

  const load = (p: number, src: string, st: string, kw: string) => {
    sessionsApi
      .list({
        agent_id: currentAgent?.agent_id ?? undefined,
        source: src || undefined,
        status: st || undefined,
        session_id: kw || undefined,
        limit: PAGE_SIZE,
        offset: (p - 1) * PAGE_SIZE,
      })
      .then((r) => {
        setRows(r.sessions)
        setTotal(r.count)
      })
      .catch(() => {})
  }
  // 切换 Agent 时回第一页并清空选中会话（load 依赖 currentAgent 才会重跑，否则残留上一 Agent 的数据）
  useEffect(() => {
    setPage(1)
    setActive(null)
    setMsgs([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentAgent?.agent_id])

  useEffect(() => {
    load(page, source, status, sid)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, source, status, sid, currentAgent?.agent_id])

  const open = async (row: SessionLedgerRow) => {
    setActive(row)
    setMsgs([])
    setMsgsLoading(true)
    try {
      const r = await sessionsApi.messages(row.session_id)
      setMsgs(r.messages)
    } catch {
      /* ignore */
    } finally {
      setMsgsLoading(false)
    }
  }

  // 深链 /obs?session=<id>（无 trace）：自动打开对应会话
  const openedRef = useRef<string | null>(null)
  useEffect(() => {
    if (traceId || !traceSession || openedRef.current === traceSession) return
    openedRef.current = traceSession
    const known = rows.find((r) => r.session_id === traceSession)
    if (known) {
      open(known)
    } else {
      setActive(null)
      setMsgs([])
      setMsgsLoading(true)
      sessionsApi
        .detail(traceSession)
        .then((d) => d.ledger && open(d.ledger))
        .catch(() => {})
        .finally(() => setMsgsLoading(false))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, traceSession, traceId])

  // 页面打开 / 筛选变化后：右侧默认选中列表第一条，不空着（有选中项且仍在列表中则保持）
  const autoRef = useRef<string | null>(null)
  useEffect(() => {
    const pendingDeep = traceSession && !traceId && openedRef.current !== traceSession
    if (pendingDeep) return // 深链会话由上面的 effect 负责打开
    if (!rows.length) {
      if (active) {
        setActive(null)
        setMsgs([])
      }
      return
    }
    const inList = active && rows.some((r) => r.session_id === active.session_id)
    const target = inList ? active : rows[0]
    if (target && target.session_id !== autoRef.current) {
      autoRef.current = target.session_id
      open(target)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, active?.session_id, traceSession, traceId])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Agent 头部（同 Agent 构建页） */}
      <div className="flex h-[56px] flex-none items-center gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-5">
        <button
          className="grid h-7 w-7 cursor-pointer place-items-center rounded-md text-[var(--muted)] hover:bg-[#EDF0F4] hover:text-[var(--ink)]"
          title="返回 Agent 首页"
          onClick={() => navigate('/')}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        </button>
        <div className="flex items-center gap-2.5">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--primary-weak)] text-[13px] font-semibold text-[var(--primary)]">
            {agentInitial(currentAgent)}
          </div>
          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold">
              {currentAgent?.name ?? currentAgent?.agent_id}
              {currentAgent?.published_version && (
                <span className="mono rounded bg-[#F1F5F9] px-1.5 py-0.5 text-[10.5px] font-normal text-[var(--ink-2)]">v{currentAgent.published_version}</span>
              )}
            </div>
            <div className="mono text-[10.5px] text-[var(--muted)]">{currentAgent?.agent_id} · 追踪与观测</div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button className="inline-flex h-7.5 items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-[12px] font-medium text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={() => alert('打开 langfuse 面板（阶段5）')}>
            打开 langfuse
          </button>
        </div>
      </div>

      {/* 顶部 tabs（贴左） */}
      <div className="flex flex-none gap-0.5 border-b border-[var(--line)] bg-[var(--surface)] px-5">
        {(
          [
            ['sessions', '会话记录'],
            ['traces', '链路历史'],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            className={`h-[38px] cursor-pointer px-4 text-[13px] ${
              tab === k ? 'border-b-2 border-[var(--primary)] font-medium text-[var(--primary)]' : 'text-[var(--ink-2)] hover:text-[var(--ink)]'
            }`}
            onClick={() => setTab(k)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'sessions' ? (
        /* ---------- 主从布局：顶部筛选行 + 会话边栏（加宽）+ 只读对话面板 ---------- */
        <>
          {/* 顶部筛选行（全宽，不占列表栏） */}
          <div className="flex flex-none flex-wrap items-center gap-2 border-b border-[var(--line)] bg-[var(--surface)] px-5 py-2">
            <div className="flex h-[30px] w-[280px] flex-none items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--bg)] px-2 text-[var(--muted)]">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
              <input
                className="min-w-0 flex-1 border-0 bg-transparent text-[12px] text-[var(--ink)] outline-none"
                placeholder="按会话 id 筛选…"
                value={sidInput}
                onChange={(e) => setSidInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    setSid(sidInput.trim())
                    setPage(1)
                  }
                }}
              />
              {sid && (
                <button className="cursor-pointer text-[11px] text-[var(--muted)] hover:text-[var(--ink)]" onClick={() => { setSid(''); setSidInput(''); setPage(1) }}>
                  ✕
                </button>
              )}
            </div>
            <div className="flex items-center gap-1">
              {(['', 'online', 'simulate', 'auto_sim'] as const).map((s) => (
                <button
                  key={s}
                  className={`h-6 cursor-pointer rounded-full px-2 text-[11px] ${
                    source === s ? 'bg-[var(--primary-weak)] font-medium text-[var(--primary)]' : 'text-[var(--ink-2)] hover:bg-[#EDF0F4]'
                  }`}
                  onClick={() => { setSource(s); setPage(1) }}
                >
                  {s === '' ? '全部渠道' : SOURCE_LABEL[s]}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1">
              {(['', 'active', 'ended'] as const).map((s) => (
                <button
                  key={s}
                  className={`h-6 cursor-pointer rounded-full px-2 text-[11px] ${
                    status === s ? 'bg-[var(--primary-weak)] font-medium text-[var(--primary)]' : 'text-[var(--ink-2)] hover:bg-[#EDF0F4]'
                  }`}
                  onClick={() => { setStatus(s); setPage(1) }}
                >
                  {s === '' ? '全部状态' : s === 'active' ? '进行中' : '已结束'}
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-2 text-[11px] text-[var(--muted)]">
              共 <b className="mono text-[var(--ink-2)]">{total}</b> 个 · 第 <b className="mono text-[var(--ink-2)]">{page}</b> / <b className="mono">{totalPages}</b> 页
              <button className="h-6 cursor-pointer rounded-md border border-[var(--line-strong)] bg-white px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>‹</button>
              <button className="h-6 cursor-pointer rounded-md border border-[var(--line-strong)] bg-white px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-45" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>›</button>
            </div>
          </div>

          <div className="relative flex min-h-0 flex-1">
            {/* 会话边栏（加宽 340，可收起） */}
            <aside
              className={`flex w-[340px] flex-none flex-col border-r border-[var(--line)] bg-[var(--surface)] transition-[margin-left] duration-200 ${
                collapsed ? '-ml-[340px]' : ''
              }`}
            >
              {/* 边栏头 */}
              <div className="flex items-center gap-2 border-b border-[var(--line)] px-3.5 py-2.5">
                <span className="flex-1 text-[13px] font-semibold">
                  会话列表 <span className="mono ml-1 text-[11px] font-normal text-[var(--muted)]">{total}</span>
                </span>
                <button
                  className="grid h-6 w-6 cursor-pointer place-items-center rounded text-[var(--muted)] hover:bg-[#EDF0F4] hover:text-[var(--ink)]"
                  title="收起会话列表"
                  onClick={() => setCollapsed(true)}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M15 19l-7-7 7-7" /></svg>
                </button>
              </div>

              {/* 会话行 */}
              <div className="flex-1 overflow-y-auto px-2 pb-2">
                {rows.map((s) => (
                  <div
                    key={s.session_id}
                    className={`mb-0.5 cursor-pointer rounded-md border px-2.5 py-2 ${
                      active?.session_id === s.session_id ? 'border-[var(--primary-line)] bg-[var(--primary-weak)]' : 'border-transparent hover:bg-[var(--bg)]'
                    }`}
                    onClick={() => open(s)}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className={`h-1.5 w-1.5 flex-none rounded-full ${s.valid ? 'bg-[var(--success)]' : 'bg-[var(--muted)]'}`} />
                      <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-[var(--ink)]">{s.title ?? '未命名会话'}</span>
                      {s.source !== 'online' && (
                        <span className="flex-none rounded bg-[var(--primary-weak)] px-1 py-0.5 text-[9.5px] text-[var(--primary)]">{SOURCE_LABEL[s.source] ?? s.source}</span>
                      )}
                    </div>
                    <div className="mono mt-0.5 truncate pl-3 text-[10px] text-[var(--muted)]">
                      {s.session_id.slice(0, 13)}… · {s.updated_at?.slice(5, 16) ?? ''}
                    </div>
                  </div>
                ))}
                {!rows.length && <div className="px-4 py-10 text-center text-[12px] text-[var(--muted)]">暂无会话记录</div>}
              </div>
            </aside>

            {/* 展开按钮（收起时贴左缘） */}
            {collapsed && (
              <button
                className="absolute left-0 top-2 z-10 grid h-6 w-6 cursor-pointer place-items-center rounded-r-md border border-l-0 border-[var(--line)] bg-[var(--surface)] text-[var(--muted)] shadow-sm hover:text-[var(--ink)]"
                title="展开会话列表"
                onClick={() => setCollapsed(false)}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M9 5l7 7-7 7" /></svg>
              </button>
            )}

            {/* 右侧：只读对话面板（一轮一轮） */}
            <div className="flex min-w-0 flex-1 flex-col bg-[var(--bg)]">
              {active ? (
                <>
                  <div className="flex flex-none items-center gap-2 border-b border-[var(--line)] bg-[var(--surface)] px-5 py-2.5">
                    <span className="max-w-[260px] truncate text-[12.5px] font-semibold text-[var(--ink)]">{active.title ?? '未命名会话'}</span>
                    <span className="mono text-[10.5px] text-[var(--muted)]">{active.session_id}</span>
                    <span className={`text-[11px] ${active.valid ? 'text-[var(--success)]' : 'text-[var(--muted)]'}`}>
                      {active.valid ? '● 进行中' : `● ${active.invalid_reason === 'timeout' ? '超时结束' : '正常结束'}`}
                    </span>
                    <span className="ml-auto text-[11px] text-[var(--muted)]">{msgs.length} 条消息 · {groupRounds(msgs).length} 轮</span>
                  </div>
                  <div className="flex-1 overflow-y-auto px-8 pb-6 pt-4">
                    <div className="mx-auto flex max-w-[760px] flex-col gap-4">
                      {msgsLoading && <div className="py-8 text-center text-[12px] text-[var(--muted)]">加载中…</div>}
                      {!msgsLoading && !msgs.length && <div className="py-8 text-center text-[12px] text-[var(--muted)]">该会话暂无消息记录</div>}
                      {groupRounds(msgs).map((r, i) => (
                        <RoundCard key={r.requestId ?? i} index={i} round={r} />
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className="grid flex-1 place-items-center">
                  <div className="text-center">
                    <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[var(--primary-weak)] text-[var(--primary)]">
                      <TraceIcon size={22} />
                    </div>
                    <div className="mt-3 text-[13px] font-medium text-[var(--ink-2)]">选择一个会话查看对话</div>
                    <div className="mt-1 text-[11.5px] text-[var(--muted)]">点击左侧会话，右侧按「轮」展示用户提问与 Agent 回复；Agent 回复可点「查看链路」</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        /* ---------- 链路历史 ---------- */
        <TraceView traceId={traceId} sessionId={traceSession} />
      )}
    </div>
  )
}

/** 一轮对话：用户提问（左）+ 该 request 的 Agent 回复（右，含查看链路）。 */
function RoundCard({ index, round }: { index: number; round: { requestId: string | null; messages: SessionMessage[] } }) {
  const navigate = useNavigate()
  const first = round.messages[0]
  const ts = first?.created_at?.slice(5, 16) ?? ''
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--surface)]">
      <div className="flex items-center gap-2 border-b border-[var(--line)] bg-[#FBFBFC] px-3 py-1.5 text-[11px] text-[var(--muted)]">
        <span className="font-medium text-[var(--ink-2)]">第 {index + 1} 轮</span>
        {round.requestId && <span className="mono">{round.requestId.slice(0, 8)}</span>}
        <span className="ml-auto">{ts}</span>
      </div>
      <div className="flex flex-col gap-3 px-3.5 py-3">
        {round.messages.map((m) => {
          const isCustomer = m.role === 'customer'
          return (
            <div key={m.message_id} className={`flex flex-col gap-1 ${isCustomer ? 'items-start' : 'items-end'}`}>
              <div className={`text-[10.5px] text-[var(--muted)] ${isCustomer ? '' : 'text-right'}`}>
                {isCustomer ? m.user_name ?? '用户' : m.agent_name ?? 'Agent'}
              </div>
              <div
                className={`max-w-[78%] whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                  isCustomer
                    ? 'rounded-tl border border-[var(--line)] bg-white'
                    : 'rounded-tr border border-[var(--primary-line)] bg-[var(--primary-weak)]'
                }`}
              >
                {m.content}
              </div>
              {!isCustomer && m.trace_id && (
                <div className="flex items-center gap-2">
                  <button
                    className="inline-flex cursor-pointer items-center gap-1 text-[11px] text-[var(--primary)] hover:underline"
                    onClick={() => navigate(`/obs?trace=${encodeURIComponent(m.trace_id!)}&session=${encodeURIComponent(m.session_id)}`)}
                  >
                    <TraceIcon size={12} />
                    查看链路
                    <span className="mono text-[10px] text-[var(--muted)]">{m.trace_id.slice(0, 8)}…</span>
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ================= 链路历史：langfuse 执行链路树（左树 + 右节点详情） ================= */

/** langfuse observation 树节点 */
interface TraceNode {
  obs: TraceObservation
  children: TraceNode[]
}

const TRACE_TYPE_META: Record<string, { label: string; cls: string }> = {
  SPAN: { label: 'span', cls: 'text-[var(--ink-2)]' },
  GENERATION: { label: 'generation · LLM', cls: 'text-[var(--primary)]' },
  EVENT: { label: 'event', cls: 'text-[var(--muted)]' },
}

/** 扁平 observations → 树（按 parentObservationId，孤儿归根）；按 startTime 稳定排序 */
function buildTraceTree(obs: TraceObservation[]): TraceNode[] {
  const byId = new Map<string, TraceNode>()
  for (const o of obs) byId.set(o.id, { obs: o, children: [] })
  const roots: TraceNode[] = []
  for (const o of obs) {
    const node = byId.get(o.id)!
    const p = o.parentObservationId ? byId.get(o.parentObservationId) : undefined
    if (p) p.children.push(node)
    else roots.push(node)
  }
  const sort = (ns: TraceNode[]) => {
    ns.sort((a, b) => (a.obs.startTime < b.obs.startTime ? -1 : a.obs.startTime > b.obs.startTime ? 1 : 0))
    ns.forEach((n) => sort(n.children))
    return ns
  }
  return sort(roots)
}

const fmtLatency = (latency?: number | null): string => {
  if (latency == null) return '—'
  if (latency < 1) return `${Math.round(latency * 1000)}ms`
  if (latency < 60) return `${latency.toFixed(2)}s`
  const m = Math.floor(latency / 60)
  return `${m}m${Math.round(latency - m * 60)}s`
}
const fmtNum = (n: number) => n.toLocaleString('en-US')
const fmtDt = (s?: string | null) => (s ? s.replace('T', ' ').slice(0, 19) : '—')

/** 轻量 JSON 高亮（不引重库）：key 紫 / 字符串绿 / 数字蓝 / 布尔·null 橙 / 标点灰 */
function JsonText({ text }: { text: string }) {
  const parts: ReactNode[] = []
  const re = /(\s*"(?:\\.|[^"\\])*"\s*:)|(\s*"(?:\\.|[^"\\])*")|(\btrue\b|\bfalse\b|\bnull\b)|(-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|([{}[\],])/g
  let last = 0
  let i = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index))
    const tok = m[0]
    const cls = m[1] ? 'text-[#7c3aed]' : m[2] ? 'text-[#047857]' : m[3] ? 'text-[#b45309]' : m[4] ? 'text-[#2563eb]' : 'text-[#94a3b8]'
    parts.push(
      <span key={i++} className={cls}>
        {tok}
      </span>,
    )
    last = m.index + tok.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <code className="font-mono text-[12px] leading-relaxed text-[var(--ink-2)]">{parts}</code>
}

/** 树节点类型图标：span=方框、generation=闪电（LLM）、event=圆点 */
function SpanIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="inline-block">
      <rect x="4" y="9" width="16" height="6" rx="1.5" />
    </svg>
  )
}
function BoltIcon({ size = 12 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className="inline-block">
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" />
    </svg>
  )
}
function DotIcon({ size = 10 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className="inline-block">
      <circle cx="12" cy="12" r="6" />
    </svg>
  )
}

/** 一条树节点（递归）：图标 + 名称 + 耗时；可折叠；点击选中 */
function TraceNodeRow({
  node,
  depth,
  selectedId,
  collapsedIds,
  onSelect,
  onToggle,
}: {
  node: TraceNode
  depth: number
  selectedId: string | null
  collapsedIds: Set<string>
  onSelect: (id: string) => void
  onToggle: (id: string) => void
}) {
  const { obs, children } = node
  const hasChildren = children.length > 0
  const collapsed = collapsedIds.has(obs.id)
  const meta = TRACE_TYPE_META[obs.type] ?? { label: obs.type, cls: 'text-[var(--ink-2)]' }
  const isErr = obs.level === 'ERROR'
  const selected = selectedId === obs.id
  return (
    <>
      <div
        className={`flex h-[26px] cursor-pointer items-center gap-1.5 rounded px-1.5 ${
          selected ? 'bg-[var(--primary-weak)]' : 'hover:bg-[#F1F5F9]'
        }`}
        style={{ paddingLeft: depth * 14 + 6 }}
        onClick={() => onSelect(obs.id)}
      >
        <button
          className="grid h-4 w-4 flex-none cursor-pointer place-items-center text-[10px] leading-none text-[var(--muted)] hover:text-[var(--ink)]"
          title={hasChildren ? (collapsed ? '展开' : '收起') : ''}
          onClick={(e) => {
            e.stopPropagation()
            if (hasChildren) onToggle(obs.id)
          }}
        >
          {hasChildren ? (collapsed ? '▸' : '▾') : '·'}
        </button>
        <span className={`flex-none leading-none ${selected ? 'text-[var(--primary)]' : meta.cls}`}>
          {obs.type === 'GENERATION' ? <BoltIcon /> : obs.type === 'EVENT' ? <DotIcon /> : <SpanIcon />}
        </span>
        <span
          className={`min-w-0 flex-1 truncate text-[12px] ${
            isErr ? 'font-medium text-[#dc2626]' : selected ? 'text-[var(--primary)]' : 'text-[var(--ink)]'
          }`}
        >
          {obs.name}
        </span>
        <span className="mono flex-none text-[10px] text-[var(--muted)]">{fmtLatency(obs.latency)}</span>
      </div>
      {hasChildren && !collapsed && (
        <div>
          {children.map((c) => (
            <TraceNodeRow key={c.obs.id} node={c} depth={depth + 1} selectedId={selectedId} collapsedIds={collapsedIds} onSelect={onSelect} onToggle={onToggle} />
          ))}
        </div>
      )}
    </>
  )
}

/** Input / Output / Metadata 展示块：JSON 高亮，超长可展开 */
function IoBlock({ label, data }: { label: string; data: unknown }) {
  const isJson = typeof data === 'object' && data !== null
  const text = isJson ? JSON.stringify(data, null, 2) : data == null ? '' : String(data)
  const long = text.length > 900
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--surface)]">
      <div className="flex items-center gap-2 border-b border-[var(--line)] px-3.5 py-2">
        <span className="text-[12px] font-semibold text-[var(--ink-2)]">{label}</span>
        <span className="mono ml-auto text-[10px] text-[var(--muted)]">{text.length} 字符</span>
        {long && (
          <button className="cursor-pointer text-[11px] text-[var(--primary)] hover:underline" onClick={() => setExpanded((v) => !v)}>
            {expanded ? '收起' : '展开'}
          </button>
        )}
      </div>
      <div className={`relative px-3.5 py-2.5 ${long && !expanded ? 'max-h-[180px] overflow-hidden' : ''}`}>
        {text ? <JsonText text={text} /> : <span className="text-[12px] text-[var(--muted)]">—</span>}
        {long && !expanded && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[48px] bg-gradient-to-t from-white to-transparent" />}
      </div>
    </div>
  )
}

/** 右侧节点详情：头 + 状态 + generation 指标 + Input/Output/Metadata + 通用标识 */
function NodeDetail({ obs }: { obs: TraceObservation }) {
  const meta = TRACE_TYPE_META[obs.type] ?? { label: obs.type, cls: 'text-[var(--ink-2)]' }
  const isErr = obs.level === 'ERROR'
  const isWarn = obs.level === 'WARNING'
  const gen = obs.type === 'GENERATION'
  const usage = obs.usageDetails
  const rows: [string, string][] = [
    ['observation id', obs.id],
    ['trace id', obs.traceId],
    ...(obs.parentObservationId ? ([['parent', obs.parentObservationId]] as [string, string][]) : []),
    ...(obs.sessionId ? ([['session', obs.sessionId]] as [string, string][]) : []),
    ...(obs.userId ? ([['user', obs.userId]] as [string, string][]) : []),
    ['开始', fmtDt(obs.startTime)],
    ...(obs.endTime ? ([['结束', fmtDt(obs.endTime)]] as [string, string][]) : []),
  ]
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-none flex-wrap items-center gap-2 border-b border-[var(--line)] bg-[var(--surface)] px-5 py-3">
        <span className="text-[13.5px] font-semibold text-[var(--ink)]">{obs.name}</span>
        <span className={`mono rounded bg-[#F1F5F9] px-1.5 py-0.5 text-[10.5px] ${meta.cls}`}>{meta.label}</span>
        {isErr && <span className="rounded bg-[#FEF2F2] px-1.5 py-0.5 text-[10.5px] font-medium text-[#dc2626]">error</span>}
        {isWarn && <span className="rounded bg-[#FFFBEB] px-1.5 py-0.5 text-[10.5px] font-medium text-[#b45309]">warning</span>}
        <span className="mono ml-auto text-[11px] text-[var(--muted)]">{fmtLatency(obs.latency)}</span>
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="mx-auto flex max-w-[860px] flex-col gap-4">
          {obs.statusMessage && (
            <div
              className={`rounded-md border px-3 py-2 text-[12px] ${
                isErr ? 'border-[#FECACA] bg-[#FEF2F2] text-[#b91c1c]' : 'border-[var(--line)] bg-[#FBFBFC] text-[var(--ink-2)]'
              }`}
            >
              {obs.statusMessage}
            </div>
          )}

          {gen && (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3.5 py-2.5 text-[12px]">
              <span className="text-[var(--ink-2)]">
                模型 <b className="mono text-[var(--ink)]">{obs.model ?? '—'}</b>
              </span>
              {usage?.input != null && (
                <span className="text-[var(--ink-2)]">
                  tokens{' '}
                  <b className="mono text-[var(--ink)]">
                    {fmtNum(usage.input)} → {fmtNum(usage.output ?? 0)}
                  </b>
                  <span className="mono ml-1 text-[var(--muted)]">(共 {fmtNum(usage.total ?? ((usage.input ?? 0) + (usage.output ?? 0)))})</span>
                </span>
              )}
              {obs.totalCost != null && (
                <span className="text-[var(--ink-2)]">
                  成本 <b className="mono text-[var(--ink)]">${obs.totalCost.toFixed(4)}</b>
                </span>
              )}
              {obs.promptName && (
                <span className="text-[var(--ink-2)]">
                  prompt <b className="mono text-[var(--ink)]">{obs.promptName}</b>
                  {obs.promptVersion != null && <span className="mono text-[var(--muted)]"> v{obs.promptVersion}</span>}
                </span>
              )}
            </div>
          )}

          <IoBlock label="Input" data={obs.input} />
          <IoBlock label="Output" data={obs.output} />
          {obs.metadata != null && <IoBlock label="Metadata" data={obs.metadata} />}

          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3.5 py-3 text-[12px]">
            {rows.map(([k, v]) => (
              <Fragment key={k}>
                <span className="text-[var(--muted)]">{k}</span>
                <span className="mono min-w-0 break-all text-[var(--ink-2)]">{v}</span>
              </Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/** 链路历史：按 traceId 查询 langfuse 执行链路；左侧整棵树 + 右侧节点详情。 */
function TraceView({ traceId, sessionId }: { traceId: string | null; sessionId: string | null }) {
  const [input, setInput] = useState(traceId ?? '')
  const [activeId, setActiveId] = useState<string | null>(null)
  const [obs, setObs] = useState<TraceObservation[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set())
  const [copied, setCopied] = useState(false)
  const reqRef = useRef(0)

  const run = (tid: string) => {
    const id = (tid ?? '').trim()
    if (!id) return
    const req = ++reqRef.current
    setActiveId(id)
    setLoading(true)
    setError(null)
    setObs(null)
    setSelectedId(null)
    setCollapsedIds(new Set())
    tracesApi
      .get(id)
      .then((r) => {
        if (req !== reqRef.current) return
        setObs(r.observations)
        const first = r.observations.find((o) => o.parentObservationId == null) ?? r.observations[0]
        if (first) setSelectedId(first.id)
      })
      .catch((e: Error) => {
        if (req !== reqRef.current) return
        setError(e.message || String(e))
      })
      .finally(() => {
        if (req === reqRef.current) setLoading(false)
      })
  }

  // 深链 /obs?trace=<id>：自动填充并查询
  useEffect(() => {
    if (traceId) {
      setInput(traceId)
      run(traceId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [traceId])

  const copy = async () => {
    if (!activeId) return
    try {
      await navigator.clipboard.writeText(activeId)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* ignore */
    }
  }

  const toggleCollapse = (id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const tree = obs ? buildTraceTree(obs) : []
  const selected = selectedId ? (obs?.find((o) => o.id === selectedId) ?? null) : null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 工具行：traceId 查询 + 复制 */}
      <div className="flex flex-none flex-wrap items-center gap-2 border-b border-[var(--line)] bg-[var(--surface)] px-5 py-2">
        <div className="flex h-[30px] w-[440px] flex-none items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--bg)] px-2 text-[var(--muted)]">
          <TraceIcon size={13} />
          <input
            className="mono min-w-0 flex-1 border-0 bg-transparent text-[12px] text-[var(--ink)] outline-none"
            placeholder="粘贴 traceId 查询执行链路…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') run(input)
            }}
          />
        </div>
        <button
          className="h-[30px] cursor-pointer rounded-md bg-[var(--primary)] px-3 text-[12px] font-medium text-white disabled:opacity-50"
          disabled={loading}
          onClick={() => run(input)}
        >
          {loading ? '查询中…' : '查询'}
        </button>
        <button
          className="inline-flex h-[30px] cursor-pointer items-center gap-1 rounded-md border border-[var(--line-strong)] bg-white px-2.5 text-[12px] text-[var(--ink-2)] hover:bg-[#F1F5F9]"
          onClick={copy}
        >
          {copied ? '已复制 ✓' : '复制 traceId'}
        </button>
        {sessionId && <span className="mono ml-auto text-[11px] text-[var(--muted)]">session {sessionId}</span>}
        {obs && <span className="mono ml-2 text-[11px] text-[var(--muted)]">{obs.length} 个节点</span>}
      </div>

      {!activeId ? (
        <div className="grid flex-1 place-items-center">
          <div className="text-center">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-[var(--primary-weak)] text-[var(--primary)]">
              <TraceIcon size={22} />
            </div>
            <div className="mt-3 text-[13px] font-medium text-[var(--ink-2)]">暂无链路</div>
            <div className="mt-1 text-[11.5px] text-[var(--muted)]">
              从「会话记录」消息旁的 <span className="inline-flex items-center gap-1 text-[var(--primary)]"><TraceIcon size={12} />查看链路</span> 进入，或在上方粘贴 traceId 查询
            </div>
          </div>
        </div>
      ) : loading ? (
        <div className="flex min-h-0 flex-1 gap-px bg-[var(--line)]">
          <div className="w-[340px] flex-none bg-[var(--surface)] p-3">
            <div className="h-6 animate-pulse rounded bg-[#EEF2F7] mb-1.5" />
            <div className="h-6 animate-pulse rounded bg-[#EEF2F7] ml-4 mb-1.5" />
            <div className="h-6 animate-pulse rounded bg-[#EEF2F7] ml-8 mb-1.5" />
            <div className="h-6 animate-pulse rounded bg-[#EEF2F7] mb-1.5" />
          </div>
          <div className="flex-1 bg-[var(--bg)] p-6">
            <div className="h-5 w-40 animate-pulse rounded bg-[#EEF2F7]" />
            <div className="mt-4 h-24 animate-pulse rounded-lg bg-[#EEF2F7]" />
            <div className="mt-3 h-24 animate-pulse rounded-lg bg-[#EEF2F7]" />
          </div>
        </div>
      ) : error ? (
        <div className="grid flex-1 place-items-center">
          <div className="max-w-[440px] text-center">
            <div className="text-[13px] font-medium text-[var(--ink-2)]">未找到该 trace 的链路数据</div>
            <div className="mono mt-1.5 break-all text-[11.5px] text-[var(--muted)]">{activeId}</div>
            <div className="mt-1 text-[11.5px] text-[var(--muted)]">{error}</div>
            <div className="mt-1 text-[11.5px] text-[var(--muted)]">可能原因：langfuse 未配置 / trace 已过期或未上报（OTLP 上报情况看 runtime 日志）</div>
            <button
              className="mt-3 h-7 cursor-pointer rounded-md border border-[var(--line-strong)] bg-white px-3 text-[12px] text-[var(--ink-2)] hover:bg-[#F1F5F9]"
              onClick={() => run(activeId)}
            >
              重试
            </button>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          {/* 左：执行链路树 */}
          <aside className="flex w-[340px] flex-none flex-col border-r border-[var(--line)] bg-[var(--surface)]">
            <div className="flex items-center gap-2 border-b border-[var(--line)] px-3.5 py-2.5">
              <span className="flex-1 text-[13px] font-semibold">执行链路</span>
              <span className="mono text-[11px] text-[var(--muted)]">{obs?.length ?? 0} 节点</span>
            </div>
            <div className="flex-1 overflow-y-auto px-2 py-1.5">
              {tree.map((n) => (
                <TraceNodeRow key={n.obs.id} node={n} depth={0} selectedId={selectedId} collapsedIds={collapsedIds} onSelect={setSelectedId} onToggle={toggleCollapse} />
              ))}
              {!tree.length && <div className="px-4 py-10 text-center text-[12px] text-[var(--muted)]">该 trace 无 observation 数据</div>}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--line)] px-3.5 py-2 text-[10.5px] text-[var(--muted)]">
              <span>图例</span>
              <span className="inline-flex items-center gap-1"><SpanIcon /> span</span>
              <span className="inline-flex items-center gap-1"><BoltIcon /> generation · LLM</span>
              <span className="inline-flex items-center gap-1"><DotIcon /> event</span>
            </div>
          </aside>

          {/* 右：节点详情 */}
          <div className="flex min-w-0 flex-1 flex-col bg-[var(--bg)]">
            {selected ? (
              <NodeDetail obs={selected} />
            ) : (
              <div className="grid flex-1 place-items-center">
                <div className="text-center">
                  <div className="text-[13px] font-medium text-[var(--ink-2)]">选择左侧节点查看详情</div>
                  <div className="mt-1 text-[11.5px] text-[var(--muted)]">左侧为完整执行链路（span / generation / event），点击节点查看输入输出</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

