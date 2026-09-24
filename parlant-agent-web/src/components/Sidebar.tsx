/** 浅色侧栏：品牌=首页入口；当前 Agent 下拉切换；平铺导航（AgentStudio 单 Agent 工作台）。 */
import { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { agentsApi } from '../api/client'
import { useApp } from '../store/app'
import { AutoIcon, BuildIcon, ChatIcon, GearIcon, PulseIcon } from './Icons'

const NAV = [
  { to: '/build', label: 'Agent 构建', Icon: BuildIcon },
  { to: '/simulate', label: '模拟对话', Icon: ChatIcon },
  { to: '/auto-sim', label: '自动仿真', Icon: AutoIcon },
  { to: '/obs', label: '追踪与观测', Icon: PulseIcon },
  { to: '/settings', label: '设置', Icon: GearIcon },
]

/** Agent 显示名：优先 agent.name，缺失回退 agent_id。 */
function agentLabel(a: { agent_id: string; name?: string | null } | null | undefined): string {
  return a?.name?.trim() || a?.agent_id || '未选择'
}

/** 头像字母：取显示名首字符（避免展示 code 时看着像缩写）。 */
function agentInitial(a: { agent_id: string; name?: string | null } | null | undefined): string {
  const s = agentLabel(a)
  return s === '未选择' ? '?' : s.slice(0, 1).toUpperCase()
}

export default function Sidebar() {
  const navigate = useNavigate()
  const { agents, currentAgent, setAgents, setCurrentAgent } = useApp()
  const [menuOpen, setMenuOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  // 加载 agent 列表；默认选第一个（已发布优先）
  useEffect(() => {
    agentsApi.list().then(setAgents).catch(() => {})
  }, [setAgents])

  useEffect(() => {
    if (agents.length && !currentAgent) {
      setCurrentAgent(
        agents.find((a) => a.loaded && a.published_version) ?? agents[0] ?? null,
      )
    }
  }, [agents, currentAgent, setCurrentAgent])

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('click', onDoc)
    return () => document.removeEventListener('click', onDoc)
  }, [])

  return (
    <aside className="fixed top-0 bottom-0 left-0 z-30 flex w-56 flex-col border-r border-[var(--line)] bg-[var(--surface)] text-[var(--ink-2)]">
      {/* 品牌：点击回首页 */}
      <div
        className="flex cursor-pointer items-center gap-2.5 border-b border-[var(--line)] px-4 py-4"
        onClick={() => navigate('/')}
      >
        <div className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--primary)] text-sm font-bold text-white">
          P
        </div>
        <div>
          <div className="text-[13px] font-semibold text-[var(--ink)]">AgentStudio</div>
          <div className="text-[10.5px] text-[var(--muted)]">Agent 工作台</div>
        </div>
      </div>

      {/* 当前 Agent：下拉切换 */}
      <div className="relative mx-3 mb-1.5 mt-3">
        <div
          ref={boxRef}
          className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-2.5 py-2 hover:bg-[#F1F5F9] hover:border-[var(--line-strong)]"
          onClick={(e) => {
            e.stopPropagation()
            setMenuOpen((v) => !v)
          }}
        >
          <span className="grid h-6 w-6 flex-none place-items-center rounded-md bg-[var(--primary)] text-[11px] font-bold text-white">
            {agentInitial(currentAgent)}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-1 text-[12.5px] font-semibold text-[var(--ink)]">
              <span className="truncate">{agentLabel(currentAgent)}</span>
              <span className="text-[10px] text-[var(--muted)]">▾</span>
            </div>
            <div className="mono truncate text-[9.5px] text-[var(--muted)]">{currentAgent?.agent_id}</div>
          </div>
          {/* 下拉列表 */}
          {menuOpen && (
            <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-50 overflow-hidden rounded-lg border border-[var(--line-strong)] bg-white shadow-[0_10px_30px_rgba(15,23,42,.14)]">
              <div className="px-3 pb-1 pt-2 text-[10.5px] font-semibold tracking-wider text-[var(--muted)]">
                切换 Agent
              </div>
              {agents.map((a) => (
                <div
                  key={a.agent_id}
                  className={`flex cursor-pointer items-center gap-2 px-3 py-2 hover:bg-[var(--bg)] ${
                    currentAgent?.agent_id === a.agent_id ? 'bg-[var(--primary-weak)]' : ''
                  }`}
                  onClick={(e) => {
                    e.stopPropagation()
                    setCurrentAgent(a)
                    setMenuOpen(false)
                  }}
                >
                  <span
                    className={`grid h-5.5 w-5.5 flex-none place-items-center rounded-md text-[10px] font-bold ${
                      currentAgent?.agent_id === a.agent_id ? 'bg-[var(--primary)] text-white' : 'bg-[var(--primary-weak)] text-[var(--primary)]'
                    }`}
                  >
                    {agentInitial(a)}
                  </span>
                  <div className="min-w-0">
                    <div className="truncate text-[12px] font-semibold text-[var(--ink)]">{agentLabel(a)}</div>
                    <div className="mono truncate text-[9.5px] text-[var(--muted)]">{a.agent_id}</div>
                  </div>
                  {currentAgent?.agent_id === a.agent_id && (
                    <span className="ml-auto text-[11px] text-[var(--primary)]">✓</span>
                  )}
                </div>
              ))}
              <div
                className="cursor-pointer border-t border-[var(--line)] px-3 py-2 text-[11.5px] text-[var(--primary)] hover:bg-[var(--primary-weak)]"
                onClick={() => {
                  setMenuOpen(false)
                  navigate('/')
                }}
              >
                ＋ 查看全部 / 创建 Agent
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 导航 */}
      <nav className="flex-1 overflow-y-auto p-2">
        {NAV.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `mb-0.5 flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] ${
                isActive
                  ? 'bg-[var(--primary-weak)] font-medium text-[var(--primary)]'
                  : 'text-[var(--ink-2)] hover:bg-[#F1F5F9] hover:text-[var(--ink)]'
              }`
            }
          >
            <Icon className="opacity-75" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="flex items-center gap-2 border-t border-[var(--line)] px-4 py-2.5 text-[11.5px] text-[var(--muted)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)]" />
        server · v3.3.1 · 运行中
      </div>
    </aside>
  )
}
