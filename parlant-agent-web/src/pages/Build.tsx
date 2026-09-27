/** Agent 构建：ctxbar + 组件导航（模块切换）+ 模块内容；草稿编辑 + 保存/发布。 */
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { agentsApi } from '../api/client'
import { useApp } from '../store/app'
import { useBuild, type BuildModule } from '../store/build'
import Basics from './build/Basics'
import Boundaries from './build/Boundaries'
import Guidelines from './build/Guidelines'
import Journey from './build/Journey'
import { Canned, Glossary, Retrievers, Tools, Variables } from './build/TableModules'
import { Observations, Relationships } from './build/Advanced'
import { DiffList } from '../components/DiffList'
import { diffDefinitions, type DefinitionDiff } from '../utils/diff'
import { agentInitial } from '../utils/agent'

const MODULES: { key: BuildModule; label: string; en: string; group: string; tip: string }[] = [
  { key: 'basics', label: '基础信息', en: 'Basics', group: 'Agent 定义', tip: 'Agent 的身份与元数据：名称/描述/语言/标签塑造它"是谁、负责什么"。配置得当能让 Agent 行为更贴合业务（docs/02-Agent实体）。' },
  { key: 'boundaries', label: '边界与开场白', en: 'Boundaries', group: 'Agent 定义', tip: '定义"能做什么 / 不能做什么"（allowed/prohibited），以及开场白与超时/错误兜底话术——把行为锁进业务红线内。' },
  { key: 'journeys', label: '旅程', en: 'Journeys', group: '上下文工程组件', tip: '多轮对话状态机，串起复杂业务流程（节点=对话/工具/分支）。示例：提前结清 = 12 个状态的完整办理流程（docs/07）。' },
  { key: 'guidelines', label: '指南', en: 'Guidelines', group: '上下文工程组件', tip: '核心行为规则：**条件 → 动作**，精确控制"什么情况下做什么"。示例：`如果客户表达投诉意向 → 转人工`（docs/04）。' },
  { key: 'observations', label: '观察', en: 'Observations', group: '上下文工程组件', tip: '**无 Action 的指南**：由对话/事件中的"观察"触发，命中即标记状态已发生，不要求智能体执行动作（docs/04 观察性指南）。' },
  { key: 'relationships', label: '关系', en: 'Relationships', group: '上下文工程组件', tip: '实体间的语义关系：依赖/蕴含/优先级/消歧——让指南、旅程、工具协同起来（docs/08）。' },
  { key: 'variables', label: '变量', en: 'Variables', group: '上下文工程组件', tip: '会话上下文数据，驱动旅程分支。示例：`isSensitive=true` 命中敏感分支、`orderList` 合同列表（docs/10）。' },
  { key: 'glossary', label: '术语表', en: 'Glossary', group: '上下文工程组件', tip: '业务术语 + 同义词，帮 LLM 准确理解用户表达。示例：`提前结清` = 提前还款 / 结清（docs/09）。' },
  { key: 'canned', label: '预设话术', en: 'Canned Responses', group: '上下文工程组件', tip: '强制使用的固定话术模板（支持 {{var}} 插值）。示例：投诉时必须原样回复的转人工话术（docs/11）。' },
  { key: 'tools', label: '工具', en: 'Tools', group: '上下文工程组件', tip: '挂接外部能力/API，Agent 按需调用。示例：`tavily_search` 联网检索、结清金额核算工具（docs/05）。' },
  { key: 'retrievers', label: '检索器', en: 'Retrievers', group: '上下文工程组件', tip: 'RAG 知识检索：从文档库取相关片段注入上下文。示例：RagFlow 业务知识库（docs/06）。' },
]

function countFor(def: unknown, key: BuildModule): number | null {
  if (!def) return null
  const d = def as Record<string, { [k: string]: unknown[] } | undefined>
  const sec = d[key === 'basics' || key === 'boundaries' ? 'agent' : key === 'canned' ? 'canned_responses' : key === 'glossary' ? 'glossary' : key === 'retrievers' ? 'retrievers' : key === 'tools' ? 'tools' : key]
  if (!sec) return null
  if (Array.isArray(sec)) return sec.length
  for (const v of Object.values(sec)) if (Array.isArray(v)) return v.length
  return null
}

export default function Build() {
  const navigate = useNavigate()
  const { currentAgent } = useApp()
  const { definition, original, module, setModule, load, markSaved, setSelected } = useBuild()
  const [publishOpen, setPublishOpen] = useState(false)
  const [newVersion, setNewVersion] = useState('')  // 留空=server 自动生成（从已发布 patch+1）
  const [busy, setBusy] = useState(false)
  // 发布前对比：已发布版本 vs 当前草稿（结构化 diff；无已发布版本 = 首次发布，视为全新增）
  const [publishLoading, setPublishLoading] = useState(false)
  const [publishDiff, setPublishDiff] = useState<DefinitionDiff | null>(null)
  const [publishVersion, setPublishVersion] = useState<string | null>(null)

  useEffect(() => {
    if (!currentAgent) {
      navigate('/')
      return
    }
    setSelected(null)
    // 构建页 = 编辑草稿：优先加载 draft 槽（agent 尚无草稿时回落已发布版本）。
    // 不能无版本 detail()——服务端缺省返回 published，重载后草稿编辑会"消失"。
    const loadDef = (v?: string) =>
      agentsApi.detail(currentAgent.agent_id, v).then((d) => {
        if (d.definition) load(currentAgent.agent_id, d.definition as never)
        return !!d.definition
      })
    loadDef('draft')
      .catch(() => false)
      .then((ok) => {
        if (!ok) loadDef(undefined).catch(() => {})
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentAgent?.agent_id])

  const dirty = useMemo(() => !!definition && !!original && JSON.stringify(definition) !== JSON.stringify(original), [definition, original])
  const version = definition?.agent.version ?? '—'

  const saveDraft = async () => {
    if (!definition) return
    setBusy(true)
    try {
      await agentsApi.create(definition as never)
      markSaved()
    } catch (err) {
      alert(`保存草稿失败：${err}`)
    } finally {
      setBusy(false)
    }
  }

  const publish = async () => {
    if (!definition) return
    setBusy(true)
    try {
      // 1) 先存草稿（槽位），2) server 自动/手动定正式版本号发布
      await agentsApi.create(definition as never)
      await agentsApi.publish(currentAgent!.agent_id, newVersion || undefined)
      markSaved()
      setPublishOpen(false)
      setNewVersion('')
      // 发布后重载（此时无草稿，定义=已发布版本）
      const d = await agentsApi.detail(currentAgent!.agent_id)
      if (d.definition) load(currentAgent!.agent_id, d.definition as never)
    } catch (err) {
      alert(`发布失败：${err}`)
    } finally {
      setBusy(false)
    }
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(definition, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${currentAgent?.agent_id ?? 'agent'}.definition.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  /** 打开发布弹窗：先对比「已发布版本 vs 当前草稿」，无变更给出提醒。 */
  const openPublish = async () => {
    if (!definition || !currentAgent) return
    setPublishOpen(true)
    setPublishLoading(true)
    setPublishDiff(null)
    try {
      const pv = currentAgent.published_version ?? null
      let published: unknown = null
      if (pv) {
        const d = await agentsApi.detail(currentAgent.agent_id, pv)
        published = d.definition
      }
      setPublishVersion(pv)
      setPublishDiff(diffDefinitions(published, definition))
    } catch {
      // 拿不到已发布定义时降级为"首次发布"对比（全新增）
      setPublishVersion(null)
      setPublishDiff(diffDefinitions(null, definition))
    } finally {
      setPublishLoading(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* ctxbar */}
      <div className="flex h-[56px] flex-none items-center gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-5">
        <button className="grid h-7 w-7 cursor-pointer place-items-center rounded-md text-[var(--muted)] hover:bg-[#EDF0F4] hover:text-[var(--ink)]" title="返回 Agent 首页" onClick={() => navigate('/')}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        </button>
        <div className="flex items-center gap-2.5">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-[var(--primary-weak)] text-[13px] font-semibold text-[var(--primary)]">{agentInitial(currentAgent)}</div>
          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold">
              {definition?.agent.name ?? currentAgent?.agent_id}
              {dirty && (
                <span className="inline-flex items-center gap-1 rounded bg-[var(--warning-weak)] px-1.5 py-0.5 text-[10.5px] font-medium text-[var(--warning)]">
                  <span className="h-1 w-1 rounded-full bg-[var(--warning)]" /> 未发布更改
                </span>
              )}
              <span className="mono rounded bg-[#F1F5F9] px-1.5 py-0.5 text-[10.5px] font-normal text-[var(--ink-2)]">v{version}</span>
            </div>
            <div className="mono text-[10.5px] text-[var(--muted)]">{currentAgent?.agent_id} · 构建工作台</div>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button className="inline-flex h-7.5 cursor-pointer items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-[12px] text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={exportJson}>导出 JSON</button>
          <button className="inline-flex h-7.5 cursor-pointer items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-[12px] text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={() => navigate('/build/versions')}>版本历史</button>
          <button className="inline-flex h-7.5 cursor-pointer items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-[12px] text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={() => navigate('/simulate')}>试跑</button>
          <button className="inline-flex h-7.5 cursor-pointer items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-3 text-[12px] text-[var(--ink-2)] hover:bg-[#F1F5F9] disabled:opacity-50" disabled={!dirty || busy} onClick={saveDraft}>保存草稿</button>
          <button className="inline-flex h-7.5 cursor-pointer items-center gap-1.5 rounded-md bg-[var(--primary)] px-3 text-[12px] font-medium text-white hover:bg-[#4338CA] disabled:opacity-50" disabled={busy} onClick={openPublish}>发布新版本</button>
        </div>
      </div>

      {/* body: comp-nav | module */}
      <div className="flex min-h-0 flex-1">
        <nav className="w-[196px] flex-none overflow-y-auto border-r border-[var(--line)] bg-[var(--surface)] p-2">
          {['Agent 定义', '上下文工程组件'].map((group) => (
            <div key={group}>
              <div className="px-2.5 pb-1 pt-2.5 text-[10.5px] text-[var(--muted)]">{group}</div>
              {MODULES.filter((m) => m.group === group).map((m) => {
                const count = countFor(definition, m.key)
                return (
                  <div
                    key={m.key}
                    title={`${m.label} · ${m.en} — ${m.tip}`}
                    className={`flex cursor-pointer items-center gap-2 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[12.5px] ${module === m.key ? 'bg-[var(--primary-weak)] font-medium text-[var(--primary)]' : 'text-[var(--ink-2)] hover:bg-[#F1F5F9]'}`}
                    onClick={() => setModule(m.key)}
                  >
                    {m.label}
                    {count !== null && <span className="mono ml-auto text-[10.5px] text-[var(--muted)]">{count}</span>}
                  </div>
                )
              })}
            </div>
          ))}
        </nav>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-[var(--bg)]">
          {/* 组件作用提示 */}
          <div className="flex flex-none items-start gap-2 border-b border-[var(--line)] bg-[#FBFCFD] px-5 py-2 text-[11.5px] leading-relaxed text-[var(--ink-2)]">
            <span className="mt-0.5 grid h-4 w-4 flex-none place-items-center rounded-full bg-[var(--primary-weak)] text-[10px] font-bold text-[var(--primary)]">?</span>
            <span>
              <b className="text-[var(--ink)]">{MODULES.find((m) => m.key === module)?.label}</b>{' '}
              <span className="mono text-[10.5px] text-[var(--muted)]">({MODULES.find((m) => m.key === module)?.en})</span> —{' '}
              {MODULES.find((m) => m.key === module)?.tip}
            </span>
          </div>
          {module === 'basics' && <Basics />}
          {module === 'boundaries' && <Boundaries />}
          {module === 'guidelines' && <Guidelines />}
          {module === 'journeys' && <Journey />}
          {module === 'variables' && <Variables />}
          {module === 'glossary' && <Glossary />}
          {module === 'canned' && <Canned />}
          {module === 'tools' && <Tools />}
          {module === 'retrievers' && <Retrievers />}
          {module === 'relationships' && <Relationships />}
          {module === 'observations' && <Observations />}
        </div>
      </div>

      {/* 发布确认弹窗 */}
      {publishOpen && (
        <div className="fixed inset-0 z-60 grid place-items-center bg-[rgba(15,23,42,.45)]" onClick={() => setPublishOpen(false)}>
          <div className="w-[540px] rounded-xl bg-[var(--surface)] p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-[15px] font-semibold">发布新版本</h3>
            <p className="mt-1 text-[12px] text-[var(--muted)]">保存当前草稿为新版本并热加载到 runtime（POST /api/agents/{'{id}'}/publish）</p>

            {/* 发布前差异对比 */}
            <div className="mt-3">
              {publishLoading ? (
                <div className="rounded-lg border border-[var(--line)] bg-[var(--bg)] p-2.5 text-[11.5px] text-[var(--muted)]">对比已发布版本中…</div>
              ) : publishDiff ? (
                publishDiff.same ? (
                  <div className="rounded-lg border border-[var(--warning)]/30 bg-[var(--warning-weak)] p-2.5 text-[12px] leading-relaxed text-[var(--warning)]">
                    ⚠ 当前草稿与已发布版本{publishVersion ? `（v${publishVersion}）` : ''}没有任何差异，确认仍要发布吗？
                  </div>
                ) : (
                  <div className="rounded-lg border border-[var(--line)] bg-[var(--bg)] p-2">
                    <div className="mb-1 px-1 text-[11px] font-semibold text-[var(--ink-2)]">
                      与已发布版本{publishVersion ? `（v${publishVersion}）` : '（首次发布）'}的差异 · 共 {publishDiff.total} 处
                    </div>
                    <div className="max-h-[200px] overflow-auto">
                      <DiffList diff={publishDiff} />
                    </div>
                  </div>
                )
              ) : null}
            </div>

            <div className="mt-4 flex flex-col gap-2">
              <label className="flex flex-col gap-1.5 text-[12px] font-medium text-[var(--ink-2)]">
                版本号 <span className="font-normal text-[var(--muted)]">（留空=自动生成，从已发布版本 patch+1）</span>
                <input className="mono h-[34px] rounded-md border border-[var(--line-strong)] px-2.5 outline-none focus:border-[var(--primary)]" placeholder="自动" value={newVersion} onChange={(e) => setNewVersion(e.target.value)} />
              </label>
            </div>
            <div className="mt-4 rounded-lg border border-[var(--line)] bg-[var(--bg)] p-2.5 text-[11.5px] leading-relaxed text-[var(--ink-2)]">
              发布后：新会话使用新版本；进行中会话保持原行为；版本永远向前，历史版本可在「版本历史」查看与对比。
            </div>
            <div className="mt-4 flex items-center gap-2.5 border-t border-[var(--line)] pt-4">
              <button className="inline-flex h-8 cursor-pointer items-center rounded-md border border-[var(--line-strong)] px-3.5 text-[12.5px] text-[var(--ink-2)]" onClick={() => setPublishOpen(false)}>取消</button>
              <div className="flex-1" />
              <button className="inline-flex h-8 cursor-pointer items-center rounded-md bg-[var(--primary)] px-4 text-[12.5px] font-medium text-white disabled:opacity-60" disabled={busy} onClick={publish}>{busy ? '发布中…' : '确认发布'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
