/** Agent 首页（onboarding）：无侧栏，全宽卡片 + 搜索 + 创建。 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { agentsApi } from '../api/client'
import type { AgentInfo } from '../api/types'
import { useApp } from '../store/app'
import { agentLabel } from '../utils/agent'

export default function Home() {
  const navigate = useNavigate()
  const { setAgents, setCurrentAgent } = useApp()
  const [agents, setLocal] = useState<AgentInfo[]>([])
  const [kw, setKw] = useState('')
  const [filter, setFilter] = useState<'all' | 'published' | 'draft'>('all')

  useEffect(() => {
    agentsApi
      .list()
      .then((list) => {
        setLocal(list)
        setAgents(list)
      })
      .catch(() => {})
  }, [setAgents])

  const shown = agents.filter((a) => {
    if (kw) {
      const k = kw.toLowerCase()
      const hit = a.agent_id.toLowerCase().includes(k) || (a.name ?? '').toLowerCase().includes(k)
      if (!hit) return false
    }
    if (filter === 'published' && !a.published_version) return false
    if (filter === 'draft' && a.published_version) return false
    return true
  })

  const enter = (a: AgentInfo) => {
    setCurrentAgent(a)
    navigate('/build')
  }

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      {/* 顶部品牌栏 */}
      <header className="sticky top-0 z-10 flex h-14 items-center border-b border-[var(--line)] bg-[var(--surface)] px-7">
        <div className="flex items-center gap-2.5">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--primary)] text-sm font-bold text-white">P</div>
          <div>
            <div className="text-sm font-semibold text-[var(--ink)]">AgentStudio</div>
            <div className="text-[10.5px] text-[var(--muted)]">Agent 工作台 · 首页</div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 text-[12.5px] font-medium text-[var(--ink-2)] hover:bg-[#F1F5F9]"
            onClick={() => alert('JSON 导入（阶段4 实现）')}
          >
            导入 JSON
          </button>
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[var(--primary)] px-3.5 text-[12.5px] font-medium text-white hover:bg-[#4338CA]"
            onClick={() => alert('创建 Agent（阶段4 实现）')}
          >
            ＋ 创建 Agent
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-[1180px] px-7 pb-12 pt-8">
        <div className="mb-5">
          <h1 className="text-[22px] font-semibold tracking-tight">Agent 首页</h1>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--ink-2)]">
            选择要进入的 Agent（点击卡片进入 Agent 构建）；进入后所有操作作用于该 Agent
            <span className="mono ml-1 text-[11.5px]">· GET /api/agents</span>
          </p>
        </div>

        {/* 搜索 + 筛选 */}
        <div className="mb-4 flex items-center gap-2.5">
          <div className="flex h-[34px] w-[320px] items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 text-[var(--muted)]">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              className="flex-1 border-0 bg-transparent text-[12.5px] text-[var(--ink)] outline-none"
              placeholder="搜索 Agent 名称 / ID…"
              value={kw}
              onChange={(e) => setKw(e.target.value)}
            />
          </div>
          {(['all', 'published', 'draft'] as const).map((f) => (
            <button
              key={f}
              className={`h-7 rounded-full px-2.5 text-[12px] ${
                filter === f ? 'bg-[var(--primary-weak)] font-medium text-[var(--primary)]' : 'text-[var(--ink-2)] hover:bg-[#EDF0F4]'
              }`}
              onClick={() => setFilter(f)}
            >
              {f === 'all' ? '全部' : f === 'published' ? '已发布' : '草稿'}
            </button>
          ))}
          <div className="ml-auto text-[12px] text-[var(--ink-2)]">
            共 <b className="mono text-[var(--ink)]">{agents.length}</b> 个 Agent
          </div>
        </div>

        {/* 卡片 */}
        <div className="grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-3.5">
          {shown.map((a) => (
            <div
              key={a.agent_id}
              className="flex cursor-pointer flex-col rounded-[11px] border border-[var(--line)] bg-[var(--surface)] p-4 transition hover:border-[var(--primary-line)] hover:shadow-[0_2px_12px_rgba(79,70,229,.06)]"
              onClick={() => enter(a)}
            >
              <div className="flex items-start gap-3">
                <div className="grid h-9 w-9 flex-none place-items-center rounded-[10px] bg-[var(--primary-weak)] text-base font-bold text-[var(--primary)]">
                  {agentLabel(a).slice(0, 1).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-[15px] font-semibold">
                    <span className="truncate">{agentLabel(a)}</span>
                    {a.published_version ? (
                      <span className="inline-flex h-5 flex-none items-center gap-1 rounded px-1.5 text-[10.5px] font-medium text-[var(--success)]">
                        <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)]" />已发布
                      </span>
                    ) : (
                      <span className="inline-flex h-5 flex-none items-center gap-1 rounded bg-[#F1F5F9] px-1.5 text-[10.5px] font-medium text-[var(--ink-2)]">
                        <span className="h-1.5 w-1.5 rounded-full bg-[#94A3B8]" />草稿
                      </span>
                    )}
                  </div>
                  <div className="mono mt-1 truncate text-[10.5px] text-[var(--muted)]">{a.agent_id}</div>
                </div>
                <div className="ml-auto text-right text-[11px] text-[var(--muted)]">
                  {a.published_version ? (
                    <>
                      当前 v<b className="text-[var(--ink-2)]">{a.published_version}</b>
                      <br />
                      <span className="text-[var(--success)]">● 已加载</span>
                    </>
                  ) : (
                    <>
                      最新 v<b className="text-[var(--ink-2)]">{a.latest_version}</b>
                      <br />
                      <span className="text-[var(--muted)]">未加载</span>
                    </>
                  )}
                </div>
              </div>
              <div className="mt-3 line-clamp-2 flex-1 text-[12px] leading-relaxed text-[var(--ink-2)]">
                {a.description?.trim() || `${agentLabel(a)} 业务说明待完善……`}
              </div>
              <div className="mt-3.5 flex items-center gap-1.5">
                <span className="text-[11px] text-[var(--ink-2)]">组件统计待接入</span>
                <span className="ml-auto cursor-pointer text-[12px] text-[var(--primary)]">进入 Agent →</span>
              </div>
            </div>
          ))}
          {/* 创建占位 */}
          <div
            className="grid cursor-pointer place-items-center rounded-[11px] border border-dashed border-[var(--line-strong)] p-4 text-center text-[var(--muted)]"
            onClick={() => alert('创建 Agent（阶段4 实现）')}
          >
            <div>
              <div className="mb-2 text-[26px] text-[var(--line-strong)]">＋</div>
              <div className="text-[13px] font-medium text-[var(--ink-2)]">创建新的 Agent</div>
              <div className="mt-1 text-[11.5px]">从 agent-definition.json 起步</div>
            </div>
          </div>
        </div>
        <div className="mt-6 text-center text-[11.5px] text-[var(--muted)]">
          AgentStudio · 所有操作作用于当前 Agent
        </div>
      </main>
    </div>
  )
}
