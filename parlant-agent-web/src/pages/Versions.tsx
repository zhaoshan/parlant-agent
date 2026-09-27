/** 版本历史：版本列表 + 任意两版本差异对比（版本向前，不做回滚覆盖 UI；deploy/快速回滚见阶段5）。 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { agentsApi } from '../api/client'
import type { AgentVersionInfo } from '../api/types'
import { useApp } from '../store/app'
import { DiffList } from '../components/DiffList'
import { diffDefinitions, type DefinitionDiff } from '../utils/diff'

const STATUS_LABEL: Record<string, string> = { published: '已发布', draft: '草稿', archived: '历史' }
const STATUS_CLS: Record<string, string> = {
  published: 'bg-[#ECFDF5] text-[#059669]',
  draft: 'bg-[#FFFBEB] text-[#B45309]',
  archived: 'bg-[#F1F5F9] text-[#64748B]',
}

export default function Versions() {
  const navigate = useNavigate()
  const { currentAgent } = useApp()
  const [versions, setVersions] = useState<AgentVersionInfo[]>([])
  const [baseVer, setBaseVer] = useState('')
  const [targetVer, setTargetVer] = useState('')
  const [diff, setDiff] = useState<DefinitionDiff | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!currentAgent) {
      navigate('/')
      return
    }
    agentsApi
      .versions(currentAgent.agent_id)
      .then((vs) => {
        setVersions(vs)
        const published = vs.find((v) => v.status === 'published')?.version
        const latest = vs[0]?.version
        // 默认对比：已发布 vs 最新（草稿优先）
        setBaseVer(published ?? latest ?? '')
        setTargetVer(vs.find((v) => v.status === 'draft')?.version ?? latest ?? '')
      })
      .catch(() => {})
  }, [currentAgent?.agent_id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!currentAgent || !baseVer || !targetVer || baseVer === targetVer) {
      setDiff(baseVer && targetVer && baseVer === targetVer ? diffDefinitions(null, null) : null)
      return
    }
    let cancelled = false
    setLoading(true)
    Promise.all([
      agentsApi.detail(currentAgent.agent_id, baseVer),
      agentsApi.detail(currentAgent.agent_id, targetVer),
    ])
      .then(([a, b]) => {
        if (!cancelled) setDiff(diffDefinitions(a.definition, b.definition))
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentAgent?.agent_id, baseVer, targetVer]) // eslint-disable-line react-hooks/exhaustive-deps

  const selOpts = useMemo(
    () => versions.map((v) => ({ value: v.version, label: `v${v.version}（${STATUS_LABEL[v.status] ?? v.status}）` })),
    [versions],
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-[56px] flex-none items-center gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-5">
        <button className="grid h-7 w-7 cursor-pointer place-items-center rounded-md text-[var(--muted)] hover:bg-[#EDF0F4] hover:text-[var(--ink)]" title="返回 Agent 构建" onClick={() => navigate('/build')}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
        </button>
        <div>
          <div className="text-[13px] font-semibold text-[var(--ink)]">{currentAgent?.name ?? currentAgent?.agent_id} · 版本历史</div>
          <div className="mono text-[10.5px] text-[var(--muted)]">{currentAgent?.agent_id} · 版本永远向前，历史版本可查看/对比</div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-[1240px] flex-1 px-6 py-5">
        {/* 版本列表 */}
        <div className="overflow-hidden rounded-[10px] border border-[var(--line)] bg-[var(--surface)]">
          <div className="border-b border-[var(--line)] px-4 py-2.5 text-[12px] font-semibold text-[var(--ink-2)]">
            版本列表（{versions.length}）
          </div>
          {versions.map((v) => (
            <div key={v.version} className="flex items-center gap-3 border-b border-[var(--line)] px-4 py-2.5 last:border-b-0 hover:bg-[#FAFBFF]">
              <span className="mono text-[12.5px] font-semibold text-[var(--ink)]">v{v.version}</span>
              <span className={`rounded px-1.5 py-0.5 text-[10.5px] font-medium ${STATUS_CLS[v.status] ?? 'bg-[#F1F5F9] text-[#64748B]'}`}>{STATUS_LABEL[v.status] ?? v.status}</span>
              <span className="mono text-[11px] text-[var(--muted)]">{v.created_by ?? '—'}</span>
              <span className="mono ml-auto text-[11px] text-[var(--muted)]">{v.updated_at?.slice(0, 19).replace('T', ' ') ?? ''}</span>
            </div>
          ))}
          {!versions.length && <div className="py-10 text-center text-[12.5px] text-[var(--muted)]">暂无版本记录</div>}
        </div>

        {/* 版本差异对比 */}
        <div className="mt-5">
          <div className="mb-2.5 flex flex-wrap items-center gap-2 text-[12.5px] text-[var(--ink-2)]">
            <span className="font-semibold">版本差异对比</span>
            <span className="text-[var(--muted)]">基准版本</span>
            <select
              className="mono h-[30px] cursor-pointer rounded-md border border-[var(--line-strong)] bg-white px-2 text-[12px] outline-none focus:border-[var(--primary)]"
              value={baseVer}
              onChange={(e) => setBaseVer(e.target.value)}
            >
              {selOpts.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <span className="text-[var(--muted)]">对比</span>
            <select
              className="mono h-[30px] cursor-pointer rounded-md border border-[var(--line-strong)] bg-white px-2 text-[12px] outline-none focus:border-[var(--primary)]"
              value={targetVer}
              onChange={(e) => setTargetVer(e.target.value)}
            >
              {selOpts.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div className="rounded-[10px] border border-[var(--line)] bg-[var(--surface)] p-3">
            {loading ? (
              <div className="py-6 text-center text-[12px] text-[var(--muted)]">对比中…</div>
            ) : diff ? (
              <DiffList diff={diff} />
            ) : (
              <div className="py-6 text-center text-[12px] text-[var(--muted)]">选择两个版本进行对比</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
