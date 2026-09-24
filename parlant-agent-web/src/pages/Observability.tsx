/** 追踪与观测（合并）：会话记录（分页）+ 链路浏览；点开会话 → 只读对话视图（无输入框）。 */
import { useEffect, useState } from 'react'
import { sessionsApi } from '../api/client'
import type { SessionLedgerRow, SessionMessage } from '../api/types'
import { TraceIcon } from '../components/Icons'

const PAGE_SIZE = 10
const SOURCE_LABEL: Record<string, string> = {
  online: '线上问答',
  simulate: '模拟对话',
  auto_sim: '自动仿真',
}

export default function Observability() {
  const [tab, setTab] = useState<'sessions' | 'traces'>('sessions')
  const [rows, setRows] = useState<SessionLedgerRow[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [source, setSource] = useState<string>('')
  const [viewing, setViewing] = useState<SessionLedgerRow | null>(null)
  const [viewMsgs, setViewMsgs] = useState<SessionMessage[]>([])
  const [viewLoading, setViewLoading] = useState(false)

  const load = (p: number, src: string) => {
    sessionsApi
      .list({ source: src || undefined, limit: PAGE_SIZE, offset: (p - 1) * PAGE_SIZE })
      .then((r) => {
        setRows(r.sessions)
        setTotal(r.count)
      })
      .catch(() => {})
  }

  useEffect(() => {
    load(page, source)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, source])

  const openView = async (row: SessionLedgerRow) => {
    setViewing(row)
    setViewMsgs([])
    setViewLoading(true)
    try {
      const r = await sessionsApi.messages(row.session_id)
      setViewMsgs(r.messages)
    } catch {
      /* ignore */
    } finally {
      setViewLoading(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-[52px] flex-none items-center border-b border-[var(--line)] bg-[var(--surface)] px-6">
        <div className="text-[13px] text-[var(--muted)]">
          追踪与观测
          {viewing && (
            <>
              {' '}
              / <span className="font-medium text-[var(--ink)]">{viewing.title ?? viewing.session_id.slice(0, 8)}</span>
            </>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button className="inline-flex h-7.5 items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-[12px] font-medium text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={() => alert('打开 langfuse 面板（阶段5）')}>
            打开 langfuse
          </button>
        </div>
      </div>

      {viewing ? (
        /* ---------- 只读对话视图（无输入框） ---------- */
        <div className="flex min-h-0 flex-1 flex-col bg-[var(--bg)]">
          <div className="border-b border-[var(--line)] bg-[var(--surface)] px-6 py-2.5">
            <button
              className="inline-flex cursor-pointer items-center gap-1 text-[12.5px] text-[var(--primary)] hover:underline"
              onClick={() => setViewing(null)}
            >
              ‹ 返回会话记录
            </button>
            <div className="mt-1.5 flex items-center gap-2 text-[12px] text-[var(--muted)]">
              <span className="font-medium text-[var(--ink)]">{viewing.title ?? '未命名会话'}</span>
              <span className="mono">{viewing.session_id}</span>
              <span className="rounded bg-[var(--primary-weak)] px-1.5 py-0.5 text-[10.5px] text-[var(--primary)]">
                {SOURCE_LABEL[viewing.source] ?? viewing.source}
              </span>
              <span className={viewing.valid ? 'text-[var(--success)]' : 'text-[var(--muted)]'}>
                {viewing.valid ? '● 进行中' : `● ${viewing.invalid_reason === 'timeout' ? '超时结束' : '正常结束'}`}
              </span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-8 pb-6 pt-5">
            <div className="mx-auto flex max-w-[720px] flex-col gap-4">
              {viewMsgs.map((m) => (
                <div key={m.message_id} className={`flex flex-col gap-1.5 ${m.role === 'customer' ? 'items-start' : 'items-end'}`}>
                  <div className={`flex items-center gap-1.5 text-[11.5px] text-[var(--muted)] ${m.role === 'agent' ? 'flex-row-reverse' : ''}`}>
                    {m.role === 'customer' ? m.user_name ?? '用户' : m.agent_name ?? 'Agent'}
                    <span className="mono text-[10px]">{m.created_at?.slice(5, 16)}</span>
                  </div>
                  <div
                    className={`max-w-[72%] whitespace-pre-wrap rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                      m.role === 'customer'
                        ? 'rounded-tl border border-[var(--line)] bg-[var(--surface)]'
                        : 'rounded-tr border border-[var(--primary-line)] bg-[var(--primary-weak)]'
                    }`}
                  >
                    {m.content}
                  </div>
                  {m.role === 'agent' && m.trace_id && (
                    <div className="flex items-center gap-2">
                      <a
                        className="inline-flex cursor-pointer items-center gap-1 text-[11px] text-[var(--primary)] hover:underline"
                        onClick={() => alert(`langfuse trace: ${m.trace_id}`)}
                      >
                        <TraceIcon size={12} />
                        查看链路
                        <span className="mono text-[10px] text-[var(--muted)]">{m.trace_id.slice(0, 8)}…</span>
                      </a>
                    </div>
                  )}
                </div>
              ))}
              {viewLoading && <div className="py-8 text-center text-[12px] text-[var(--muted)]">加载中…</div>}
              {!viewLoading && !viewMsgs.length && (
                <div className="py-8 text-center text-[12px] text-[var(--muted)]">该会话暂无消息记录</div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* ---------- 列表 ---------- */
        <div className="mx-auto w-full max-w-[1240px] flex-1 px-6 py-5">
          <div className="mb-4">
            <h1 className="text-[19px] font-semibold tracking-tight">追踪与观测</h1>
            <p className="mt-0.5 text-[12.5px] text-[var(--ink-2)]">会话记录（MySQL 台账 + 每轮 trace_id）+ 链路浏览 · 合并视图</p>
          </div>

          {/* tabs */}
          <div className="mb-4 flex gap-0.5 border-b border-[var(--line)]">
            {(
              [
                ['sessions', `会话记录 ${total}`],
                ['traces', '链路浏览'],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                className={`h-[38px] cursor-pointer px-4 text-[13px] ${
                  tab === k
                    ? 'border-b-2 border-[var(--primary)] font-medium text-[var(--primary)]'
                    : 'text-[var(--ink-2)] hover:text-[var(--ink)]'
                }`}
                onClick={() => setTab(k)}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === 'sessions' && (
            <>
              <div className="mb-3 flex items-center gap-2">
                {(['', 'online', 'simulate', 'auto_sim'] as const).map((s) => (
                  <button
                    key={s}
                    className={`h-7 rounded-full px-2.5 text-[12px] ${
                      source === s ? 'bg-[var(--primary-weak)] font-medium text-[var(--primary)]' : 'text-[var(--ink-2)] hover:bg-[#EDF0F4]'
                    }`}
                    onClick={() => {
                      setSource(s)
                      setPage(1)
                    }}
                  >
                    {s === '' ? '全部' : SOURCE_LABEL[s]}
                  </button>
                ))}
                <div className="ml-auto text-[12px] text-[var(--ink-2)]">共 <b className="mono text-[var(--ink)]">{total}</b> 个会话</div>
              </div>

              <div className="overflow-hidden rounded-[10px] border border-[var(--line)] bg-[var(--surface)]">
                {rows.map((s) => (
                  <div
                    key={s.session_id}
                    className="flex cursor-pointer items-center gap-3.5 border-b border-[var(--line)] px-4 py-3 last:border-b-0 hover:bg-[#FAFBFF]"
                    onClick={() => openView(s)}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-[13px] font-semibold">
                        <span className={`h-1.5 w-1.5 flex-none rounded-full ${s.valid ? 'bg-[var(--success)]' : 'bg-[var(--muted)]'}`} />
                        {s.title ?? '未命名会话'}
                        {s.source !== 'online' && (
                          <span className="rounded bg-[var(--primary-weak)] px-1.5 py-0.5 text-[10px] font-normal text-[var(--primary)]">
                            {SOURCE_LABEL[s.source]}
                          </span>
                        )}
                      </div>
                      <div className="mono mt-0.5 text-[10.5px] text-[var(--muted)]">{s.session_id}</div>
                    </div>
                    <div className="w-[120px] text-[12px] text-[var(--ink-2)]">
                      {s.agent_id}
                      <div className="mono mt-0.5 text-[10px] text-[var(--muted)]">{s.user_id}</div>
                    </div>
                    <div className="w-[150px] text-[12px] text-[var(--ink-2)]">
                      {s.valid ? (
                        <span className="text-[var(--success)]">进行中</span>
                      ) : (
                        <span className="text-[var(--muted)]">{s.invalid_reason === 'timeout' ? '超时结束' : '正常结束'}</span>
                      )}
                      <div className="mt-0.5 text-[10.5px] text-[var(--muted)]">{s.updated_at?.slice(5, 16)}</div>
                    </div>
                    <div className="w-[90px] text-right text-[12px] text-[var(--ink-2)]">查看 ›</div>
                  </div>
                ))}
                {!rows.length && <div className="py-10 text-center text-[12.5px] text-[var(--muted)]">暂无会话记录</div>}
              </div>

              {/* 分页 */}
              <div className="mt-3 flex items-center gap-3">
                <span className="text-[12px] text-[var(--ink-2)]">
                  第 <b className="mono text-[var(--ink)]">{page}</b> / <b className="mono text-[var(--ink)]">{totalPages}</b> 页 · 每页 {PAGE_SIZE}
                </span>
                <div className="ml-auto flex gap-1.5">
                  <button
                    className="h-7 cursor-pointer rounded-md border border-[var(--line-strong)] bg-white px-3 text-[12px] text-[var(--ink-2)] disabled:cursor-not-allowed disabled:opacity-45"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    ‹ 上一页
                  </button>
                  <button
                    className="h-7 cursor-pointer rounded-md border border-[var(--line-strong)] bg-white px-3 text-[12px] text-[var(--ink-2)] disabled:cursor-not-allowed disabled:opacity-45"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    下一页 ›
                  </button>
                </div>
              </div>
            </>
          )}

          {tab === 'traces' && (
            <div className="rounded-[10px] border border-[var(--line)] bg-[var(--surface)] py-14 text-center">
              <div className="text-[13px] font-medium text-[var(--ink-2)]">链路浏览（规划中）</div>
              <div className="mt-1.5 text-[12px] text-[var(--muted)]">后续聚合 langfuse trace 列表或内嵌面板；当前以「会话记录 → 每轮链路」跳转详情</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
