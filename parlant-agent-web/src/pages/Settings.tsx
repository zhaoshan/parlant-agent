/** 设置页：运行时模型/版本 + Agent 管理（删除）——平台级基础能力。 */
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { agentsApi, settingsApi } from '../api/client'
import type { SettingsInfo } from '../api/types'
import { useApp } from '../store/app'
import { agentLabel } from '../utils/agent'

interface StatusProps {
  label: string
  value?: string
  mono?: boolean
  ok?: boolean
}
function Row({ label, value, mono, ok }: StatusProps) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <div className="w-28 flex-none text-[12px] text-[var(--ink-2)]">{label}</div>
      <div className={`min-w-0 flex-1 truncate text-[12.5px] ${mono ? 'font-mono text-[11.5px]' : ''} ${value ? 'text-[var(--ink)]' : 'text-[var(--muted)]'}`}>
        {value || '—'}
      </div>
      {ok !== undefined && (
        <span
          className={`inline-flex flex-none items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] ${
            ok ? 'bg-[#ECFDF5] text-[#047857]' : 'bg-[#FEF2F2] text-[#B91C1C]'
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-[#059669]' : 'bg-[#DC2626]'}`} />
          {ok ? '正常' : '异常'}
        </span>
      )}
    </div>
  )
}

function Card({ title, desc, children }: { title: string; desc?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface)]">
      <div className="border-b border-[var(--line)] px-5 py-3.5">
        <div className="text-[13px] font-semibold text-[var(--ink)]">{title}</div>
        {desc && <div className="mt-0.5 text-[11.5px] text-[var(--muted)]">{desc}</div>}
      </div>
      <div className="px-5 py-2">{children}</div>
    </section>
  )
}

export default function Settings() {
  const { agents, setAgents, currentAgent, setCurrentAgent } = useApp()
  const navigate = useNavigate()
  const [settings, setSettings] = useState<SettingsInfo | null>(null)
  const [loadErr, setLoadErr] = useState('')
  // 删除确认弹窗
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [typedName, setTypedName] = useState('')
  const [deleting, setDeleting] = useState(false)

  const refresh = () => agentsApi.list().then(setAgents).catch(() => {})
  useEffect(() => {
    refresh()
    settingsApi
      .get()
      .then(setSettings)
      .catch((e) => setLoadErr(String(e)))
  }, [])

  // 「删除当前 Agent」必须输入 Agent 名称精确匹配才可确认
  const currentInfo = currentAgent ? agents.find((a) => a.agent_id === currentAgent.agent_id) : null
  const currentName = currentAgent ? agentLabel(currentAgent) : ''
  const nameMatched = typedName.trim() === currentName && currentName.length > 0

  const openConfirm = () => {
    setTypedName('')
    setConfirmOpen(true)
  }
  const doDelete = async () => {
    if (!currentAgent || !nameMatched) return
    setDeleting(true)
    try {
      await agentsApi.deleteAgent(currentAgent.agent_id)
      setConfirmOpen(false)
      setCurrentAgent(null)
      refresh()
      // Agent 已删除，回首页看列表
      navigate('/')
    } catch (e) {
      alert(`删除失败：${e}`)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-[52px] flex-none items-center border-b border-[var(--line)] bg-[var(--surface)] px-6">
        <div className="text-[13px] font-semibold text-[var(--ink)]">设置</div>
      </div>

      <div className="mx-auto w-full max-w-[820px] flex-1 space-y-5 overflow-y-auto px-7 py-6">
        {/* 运行时 */}
        <Card title="运行时" desc="执行引擎（parlant-agent-runtime）当前使用的模型与版本；LLM/向量模型来自 runtime 进程配置。">
          {loadErr && <div className="py-2 text-[11.5px] text-[var(--danger)]">设置加载失败：{loadErr}</div>}
          {!settings && !loadErr && <div className="py-3 text-[12px] text-[var(--muted)]">加载中…</div>}
          {settings && (
            <div className="divide-y divide-[var(--line)]">
              <Row label="运行状态" ok={!settings.runtime_unreachable} value={settings.runtime_unreachable ? 'runtime 不可达' : settings.runtime?.service} mono />
              <Row label="LLM 模型" value={settings.runtime?.main_llm_model} mono />
              <Row label="向量模型" value={settings.runtime?.embedding_model} mono />
              <Row label="Parlant" value={settings.runtime?.parlant_version} mono />
            </div>
          )}
        </Card>

        {/* langfuse */}
        <Card title="可观测（langfuse）" desc="执行链路追踪接入状态；数据经 server 代理读取。">
          {settings && (
            <div className="divide-y divide-[var(--line)]">
              <Row label="接入" ok={settings.langfuse.configured} value={settings.langfuse.configured ? '已配置' : '未配置'} />
              {settings.langfuse.base_url && <Row label="Base URL" value={settings.langfuse.base_url} mono />}
            </div>
          )}
        </Card>

        {/* 当前 Agent */}
        <Card title="当前 Agent" desc="设置作用于当前选中的 Agent；删除为逻辑删除：卸载运行时，定义仍保留在 Mongo（可恢复），只是不再展示。">
          {!currentAgent ? (
            <div className="py-3 text-[12px] text-[var(--muted)]">未选择 Agent（回首页选择一个再回来操作）</div>
          ) : (
            <div className="divide-y divide-[var(--line)]">
              <Row label="名称" value={agentLabel(currentAgent)} />
              <Row label="Agent id" value={currentAgent.agent_id} mono />
              <Row label="状态" value={currentInfo ? currentInfo.latest_status : currentAgent.latest_status} mono />
              <div className="flex items-center justify-between gap-3 py-3">
                <div className="text-[11.5px] text-[var(--muted)]">字面删除当前 Agent；操作前需输入名称二次确认。</div>
                <button
                  className="inline-flex h-7.5 flex-none items-center rounded-md border border-[#FECACA] px-3.5 text-[12px] font-medium text-[#B91C1C] hover:bg-[#FEF2F2]"
                  onClick={openConfirm}
                >
                  删除当前 Agent
                </button>
              </div>
            </div>
          )}
        </Card>

        <div className="pb-4 text-center text-[11.5px] text-[var(--muted)]">AgentStudio · 平台设置</div>
      </div>

      {/* 删除确认弹窗：必须精确输入 Agent 名称 */}
      {confirmOpen && currentAgent && (
        <div className="fixed inset-0 z-60 grid place-items-center bg-[rgba(15,23,42,.45)]" onClick={() => !deleting && setConfirmOpen(false)}>
          <div className="w-[480px] rounded-xl bg-[var(--surface)] p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-[15px] font-semibold">删除当前 Agent</h3>
                <p className="mt-1 text-[12px] text-[var(--muted)]">
                  将卸载运行时并逻辑删除
                  <span className="mono ml-1">({currentAgent.agent_id})</span>
                  。定义保留在 Mongo，可恢复。
                </p>
              </div>
              <button className="cursor-pointer rounded-md p-1 text-[var(--muted)] hover:bg-[#EDF0F4]" onClick={() => !deleting && setConfirmOpen(false)}>✕</button>
            </div>

            <div className="mt-4 flex flex-col gap-1.5">
              <label className="text-[12px] font-medium text-[var(--ink-2)]">
                请输入 <span className="mono text-[#B91C1C]">{currentName}</span> 以确认删除
              </label>
              <input
                autoFocus
                className="mono h-9 w-full rounded-md border border-[var(--line-strong)] bg-[var(--bg)] px-2.5 text-[12px] text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)]"
                placeholder="输入 Agent 名称"
                value={typedName}
                onChange={(e) => setTypedName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && nameMatched && doDelete()}
              />
              {typedName.trim() !== '' && !nameMatched && (
                <div className="text-[11px] text-[var(--danger)]">名称不匹配，请核对后重输</div>
              )}
            </div>

            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                className="inline-flex h-8 items-center rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 text-[12.5px] font-medium text-[var(--ink-2)] hover:bg-[#F1F5F9]"
                onClick={() => !deleting && setConfirmOpen(false)}
                disabled={deleting}
              >
                取消
              </button>
              <button
                className="inline-flex h-8 items-center rounded-md bg-[#DC2626] px-3.5 text-[12.5px] font-medium text-white hover:bg-[#B91C1C] disabled:cursor-not-allowed disabled:opacity-40"
                onClick={doDelete}
                disabled={!nameMatched || deleting}
              >
                {deleting ? '删除中…' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}