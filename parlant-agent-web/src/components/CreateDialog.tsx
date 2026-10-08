/** 创建 Agent 对话框：填名称（可选 id）→ 生成空定义 → 存草稿 → 进入构建页。
 * 与 ImportDialog 同交互循环：POST /api/agents 保存为草稿后，onCreated(agentId) 交 Home 刷列表并行进构建页。
 */
import { useEffect, useRef, useState } from 'react'
import { agentsApi } from '../api/client'
import { newAgentDefinition } from '../utils/agent'

interface Props {
  onClose: () => void
  onCreated: (agentId: string) => void
}

export default function CreateDialog({ onClose, onCreated }: Props) {
  const [name, setName] = useState('')
  // agent_id 默认给随机值（不跟随名称），用户可手改；创建后不可改
  const [id, setId] = useState(() => `agent-${Math.random().toString(16).slice(2, 8)}`)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  // 已存在的 agent_id 集合（挂载时拉一次，用于查重——不可再被复用）
  const [existingIds, setExistingIds] = useState<Map<string, string> | null>(null)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    agentsApi
      .list()
      .then((list) => setExistingIds(new Map(list.map((a) => [a.agent_id, a.name || a.agent_id]))))
      .catch(() => setExistingIds(new Map()))
  }, [])

  const idTrim = id.trim()
  // 命中已存在 agent → 阻止创建（服务端对已存在 id 是「保存草稿」语义，复用会覆盖既有草稿）
  const dupId = existingIds !== null ? existingIds.get(idTrim) : undefined
  const canCreate = name.trim().length > 0 && idTrim.length > 0 && !dupId && !busy

  const doCreate = async () => {
    if (!canCreate) return
    setBusy(true)
    setErr('')
    try {
      const def = newAgentDefinition(id.trim(), name.trim())
      const created = await agentsApi.create(def, true)
      onCreated(created.agent_id)
    } catch (e) {
      setErr(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-60 grid place-items-center bg-[rgba(15,23,42,.45)]" onClick={onClose}>
      <div className="w-[480px] rounded-xl bg-[var(--surface)] p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-[15px] font-semibold">创建新的 Agent</h3>
            <p className="mt-1 text-[12px] text-[var(--muted)]">
              先生成一份空定义（各组件留空表），保存为草稿后进入构建页逐步配置
              <span className="mono ml-1">（POST /api/agents）</span>
            </p>
          </div>
          <button className="cursor-pointer rounded-md p-1 text-[var(--muted)] hover:bg-[#EDF0F4]" onClick={onClose}>✕</button>
        </div>

        <div className="mt-4 space-y-3.5">
          <div className="flex flex-col gap-1.5">
            <label className="text-[12px] font-medium text-[var(--ink-2)]">
              Agent 名称<span className="text-[var(--danger)]">*</span>
            </label>
            <input
              ref={nameRef}
              autoFocus
              className="h-9 w-full rounded-md border border-[var(--line-strong)] bg-[var(--bg)] px-2.5 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)]"
              placeholder="如：提前结清助手"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && canCreate && doCreate()}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-[12px] font-medium text-[var(--ink-2)]">
              Agent id<span className="text-[var(--danger)]">*</span>
              <span className="ml-1 font-normal text-[var(--muted)]">唯一标识，创建后不可改；默认随机生成，可自行修改</span>
            </label>
            <input
              className={`mono h-9 w-full rounded-md border px-2.5 text-[12px] text-[var(--ink)] outline-none focus:shadow-[0_0_0_3px_var(--primary-weak)] ${
                dupId ? 'border-[#F87171] focus:border-[#F87171]' : 'border-[var(--line-strong)] focus:border-[var(--primary)]'
              }`}
              placeholder="agent-xxxxxx"
              value={id}
              onChange={(e) => setId(e.target.value)}
            />
            {dupId && (
              <div className="text-[11px] text-[var(--danger)]">
                agent_id 已被占用（{dupId}）——重复 id 会当作「保存草稿」覆盖该 Agent，请改用其它 id
              </div>
            )}
          </div>
        </div>

        {err && (
          <div className="mt-3 rounded-lg border border-[#FECACA] bg-[#FEF2F2] p-2.5 text-[11.5px] text-[var(--danger)]">
            {err}
            <div className="mt-0.5 text-[11px] opacity-70">可改用其它 agent_id 或名称重试</div>
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            className="inline-flex h-8 items-center rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3.5 text-[12.5px] font-medium text-[var(--ink-2)] hover:bg-[#F1F5F9]"
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[var(--primary)] px-3.5 text-[12.5px] font-medium text-white hover:bg-[#4338CA] disabled:cursor-not-allowed disabled:opacity-40"
            onClick={doCreate}
            disabled={!canCreate}
          >
            {busy ? '创建中…' : '创建并进入构建'}
          </button>
        </div>
      </div>
    </div>
  )
}