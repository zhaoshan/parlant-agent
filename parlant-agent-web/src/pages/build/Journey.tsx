/** 旅程：顶部可收缩「基本信息」+ 左侧状态列表 + 右侧表单编辑/流程图展示。 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { JourneyDef, JourneyStateDef } from '../../api/agentDefinition'
import { useBuild } from '../../store/build'
import { ChevronDown } from '../../components/Icons'
import { ChipsInput, F, MultiSelect, Select, Switch, TextInput } from './fields'

const NODE_COLOR: Record<string, { bg: string; text: string }> = {
  chat: { bg: '#EEF2FF', text: '#4F46E5' },
  tool: { bg: '#ECFDF5', text: '#059669' },
  fork: { bg: '#FFFBEB', text: '#B45309' },
  end: { bg: '#F1F5F9', text: '#475569' },
}
const gid = (p: string) => `${p}_${Math.random().toString(36).slice(2, 8)}`

/** 组合模式（loader 只认这 4 个值；loose 无效会静默回落 fluid，故不提供） */
const COMPOSITION_OPTIONS = [
  { value: 'fluid', label: 'fluid · 自由生成' },
  { value: 'composited', label: 'composited · 拟话术' },
  { value: 'canned_composited', label: 'canned_composited · 拟话术(仅话术源)' },
  { value: 'strict', label: 'strict · 仅话术' },
]
const COMPOSITION_TIP =
  'fluid=引擎自由生成，指南/话术仅作参考；composited=回复在措辞上模仿绑定话术（与 canned_composited 在 v3.3.1 引擎等效）；strict=只能基于绑定话术输出，不自由发挥。'

export default function Journey() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const [journeyId, setJourneyId] = useState<string | null>(null)
  const [view, setView] = useState<'form' | 'graph'>('form')
  const [infoOpen, setInfoOpen] = useState(false)
  if (!definition) return null
  const journeys = definition.journeys?.journeys ?? []
  const jid = journeyId && journeys.some((j) => j.id === journeyId) ? journeyId : journeys[0]?.id ?? null
  const journey = journeys.find((j) => j.id === jid) ?? null
  const states = journey?.states ?? []
  const curState = states.find((s) => s.id === selectedId) ?? null

  const updateJourney = (patch: Partial<JourneyDef>) => {
    if (!journey) return
    update((d) => (d.journeys!.journeys = d.journeys!.journeys.map((j) => (j.id === journey.id ? { ...j, ...patch } : j))))
  }
  const updateState = (id: string, patch: Partial<JourneyStateDef>) => {
    if (!journey) return
    update((d) => {
      const j = d.journeys!.journeys.find((x) => x.id === journey.id)
      if (j) j.states = j.states!.map((s) => (s.id === id ? { ...s, ...patch } : s))
    })
  }
  const newJourney = () => {
    const id = gid('jny')
    const entry = gid('sta')
    update((d) =>
      d.journeys!.journeys.push({
        id,
        title: '新旅程',
        description: '',
        sop_type: 'main',
        priority: 1,
        entry_node: entry,
        status: 'alive',
        triggers: [],
        states: [{ id: entry, title: '入口', type: 'chat', chat_state: '', transitions: [] }],
      }),
    )
    setJourneyId(id)
    setSelected(entry)
  }
  const deleteJourney = () => {
    if (!journey) return
    const refs = (definition.guidelines?.guidelines ?? []).filter((g) => (g.journey_ids ?? []).includes(journey.id)).length
    const extra = refs ? `（有 ${refs} 条指南绑定它，删除后这些指南将不绑定旅程）` : ''
    if (!window.confirm(`删除旅程「${journey.title}」？${extra}`)) return
    update((d) => (d.journeys!.journeys = d.journeys!.journeys.filter((j) => j.id !== journey.id)))
    setJourneyId(null)
    setSelected(null)
  }

  if (!journey) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-[13px] text-[var(--muted)]">
        暂无旅程
        <button className="inline-flex h-8 cursor-pointer items-center rounded-md bg-[var(--primary)] px-4 text-[12.5px] font-medium text-white" onClick={newJourney}>＋ 新建旅程</button>
      </div>
    )
  }

  const nextStateOptions = states.map((s) => ({ value: s.id, label: s.title }))
  const toolOptions = (definition.tools?.tools ?? []).map((t) => ({ value: t.id ?? t.name, label: t.name }))
  const cannedOptions = (definition.canned_responses?.responses ?? []).map((c) => ({ value: c.id, label: c.template.slice(0, 36) }))
  const retrieverOptions = (definition.retrievers?.retrievers ?? []).map((r) => ({ value: r.id, label: r.title }))

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 顶部：旅程选择 + 新建 + 视图切换 */}
      <div className="flex items-center gap-2 border-b border-[var(--line)] bg-[var(--surface)] px-3 py-2">
        <Select className="w-[240px] flex-none" value={jid} onChange={(v) => { setJourneyId(v); setSelected(null) }} options={journeys.map((j) => ({ value: j.id, label: j.title }))} />
        <button className="grid h-6 w-6 flex-none cursor-pointer place-items-center rounded bg-[var(--primary-weak)] text-[14px] text-[var(--primary)]" title="新建旅程" onClick={newJourney}>＋</button>
        <button className="grid h-6 w-6 flex-none cursor-pointer place-items-center rounded text-[var(--muted)] hover:bg-[#FEF2F2] hover:text-[var(--danger)]" title="删除当前旅程" onClick={deleteJourney}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6h14z"/></svg>
        </button>
        <div className="ml-2 flex items-center gap-1">
          {(['form', 'graph'] as const).map((v) => (
            <button key={v} className={`h-7 cursor-pointer rounded-md px-3 text-[12px] ${view === v ? 'bg-[var(--primary-weak)] font-medium text-[var(--primary)]' : 'text-[var(--ink-2)] hover:bg-[#F1F5F9]'}`} onClick={() => setView(v)}>
              {v === 'form' ? '表单编辑' : '流程图'}
            </button>
          ))}
        </div>
        <span className="ml-auto text-[11px] text-[var(--muted)]">
          {view === 'form' ? '指定当前节点的下一状态（表单）' : '展示 + 校验节点关系（点击节点回表单编辑）'}
        </span>
      </div>

      {/* 顶部：可收缩 基本信息 */}
      <div className="flex-none border-b border-[var(--line)] bg-[var(--surface)]">
        <div className="flex cursor-pointer items-center gap-2 px-4 py-2 hover:bg-[#FAFBFF]" onClick={() => setInfoOpen((v) => !v)}>
          <ChevronDown size={13} className={`transition-transform ${infoOpen ? 'rotate-0' : '-rotate-90'}`} />
          <span className="text-[12.5px] font-semibold text-[var(--ink)]">基本信息</span>
          <span className="truncate text-[11.5px] text-[var(--muted)]">
            {journey.title} · 入口 {stateOfTitle(journey.entry_node, states)} · {states.length} 状态 · {journey.priority ?? 0} 优先级
            {infoOpen ? '' : '（点击展开编辑）'}
          </span>
        </div>
        {infoOpen && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 pb-4 pt-1 lg:grid-cols-3">
            <F label="旅程标题" full>
              <TextInput value={journey.title} onChange={(v) => updateJourney({ title: v })} />
            </F>
            <F label="入口节点">
              <Select value={journey.entry_node ?? ''} onChange={(v) => updateJourney({ entry_node: v })} options={nextStateOptions} />
            </F>
            <F label="组合模式" tip={COMPOSITION_TIP}>
              <Select value={journey.composition_mode ?? 'fluid'} onChange={(v) => updateJourney({ composition_mode: v })} options={COMPOSITION_OPTIONS} />
            </F>
            <F label="优先级 Priority">
              <TextInput mono value={String(journey.priority ?? 0)} onChange={(v) => updateJourney({ priority: Number(v) || 0 })} />
            </F>
            <F label="触发器 Triggers" hint="识别到该意图时进入旅程" full>
              <TextInput rows={2} value={(journey.triggers ?? []).join('\n')} onChange={(v) => updateJourney({ triggers: v.split('\n').filter(Boolean) })} />
            </F>
            <F label="描述 Description" full>
              <TextInput rows={2} value={journey.description ?? ''} onChange={(v) => updateJourney({ description: v })} />
            </F>
            <F label="业务目标 Business Goal" hint="SOP 说明（schema 字段）" full>
              <TextInput rows={2} value={journey.business_goal ?? ''} onChange={(v) => updateJourney({ business_goal: v })} />
            </F>
          </div>
        )}
      </div>

      {/* body：左状态列表 + 右表单/流程图 */}
      <div className="flex min-h-0 flex-1">
        {/* 状态列表 */}
        <div className="flex w-[280px] flex-none flex-col border-r border-[var(--line)] bg-[var(--surface)]">
          <div className="flex items-center px-3 py-2 text-[11px] font-semibold text-[var(--muted)]">
            状态（{states.length}）
            <button className="ml-auto cursor-pointer text-[11px] font-normal text-[var(--primary)]" onClick={() => { const id = gid('sta'); update((d) => { const j = d.journeys!.journeys.find((x) => x.id === journey.id); j?.states?.push({ id, title: '新节点', type: 'chat', chat_state: '', transitions: [] }) }); setSelected(id) }}>＋ 新建节点</button>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {states.map((s) => {
              const color = NODE_COLOR[s.type] ?? NODE_COLOR.chat
              return (
                <div key={s.id} className={`mb-0.5 flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 ${selectedId === s.id ? 'border-[var(--primary-line)] bg-[var(--primary-weak)]' : 'border-transparent hover:bg-[var(--bg)]'}`} onClick={() => setSelected(s.id)}>
                  <span className="h-2 w-2 flex-none rounded-full" style={{ background: color.text }} />
                  <div className="min-w-0">
                    <div className="truncate text-[12.5px] font-medium text-[var(--ink)]">{s.title}</div>
                    <div className="mono text-[10px] text-[var(--muted)]">{s.type} · {(s.transitions ?? []).length} 出边</div>
                  </div>
                  {s.id === journey.entry_node && <span className="ml-auto rounded bg-[#1E293B] px-1 py-0.5 text-[8.5px] font-bold text-white">ENTRY</span>}
                </div>
              )
            })}
          </div>
        </div>

        {/* 右列 */}
        <div className="flex min-w-0 flex-1 flex-col">
          {view === 'form' ? (
            /* -------- 表单编辑 -------- */
            <div className="flex-1 overflow-y-auto bg-[var(--surface)]">
              {curState ? (
                <div className="max-w-[640px] p-5">
                  <div className="mb-4 flex items-center gap-2">
                    <span className="text-[13px] font-semibold">编辑节点</span>
                    <span className="mono text-[10.5px] text-[var(--muted)]">{curState.id}</span>
                    <button className="ml-auto cursor-pointer text-[12px] text-[var(--danger)]" onClick={() => { update((d) => { const j = d.journeys!.journeys.find((x) => x.id === journey.id); j!.states = j!.states!.filter((s) => s.id !== curState.id) }); setSelected(null) }}>删除节点</button>
                  </div>
                  <F label="标题"><TextInput value={curState.title} onChange={(v) => updateState(curState.id, { title: v })} /></F>
                  <div className="mt-3">
                    <F label="节点类型">
                      <Select value={curState.type} onChange={(v) => updateState(curState.id, { type: v as JourneyStateDef['type'] })} options={[{ value: 'chat', label: 'chat 对话' }, { value: 'tool', label: 'tool 工具' }, { value: 'fork', label: 'fork 分支' }, { value: 'end', label: 'end 终态' }]} />
                    </F>
                  </div>
                  <div className="mt-3">
                    <F label={curState.type === 'tool' ? '工具指令 Tool Instruction' : '会话状态 Chat State'} hint="进入该节点后 Agent 的行为/话术">
                      <TextInput rows={4} value={(curState.type === 'tool' ? curState.tool_instruction : curState.chat_state) ?? ''} onChange={(v) => updateState(curState.id, curState.type === 'tool' ? { tool_instruction: v } : { chat_state: v })} />
                    </F>
                  </div>
                  <div className="mt-3">
                    <F label="描述 Description"><TextInput rows={2} value={curState.description ?? ''} onChange={(v) => updateState(curState.id, { description: v })} /></F>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-4">
                    <F label="组合模式" tip={COMPOSITION_TIP}>
                      <Select value={curState.composition_mode ?? 'fluid'} onChange={(v) => updateState(curState.id, { composition_mode: v })} options={COMPOSITION_OPTIONS} />
                    </F>
                    <F label="优先级 Priority"><TextInput mono value={String(curState.priority ?? 0)} onChange={(v) => updateState(curState.id, { priority: Number(v) || 0 })} /></F>
                  </div>
                  {curState.type === 'tool' && (
                    <div className="mt-3">
                      <F label="调用工具 Tool State" hint="tool 节点真正调用的工具（含内置 variable_update / journey_node_counter）">
                        <MultiSelect options={toolOptions} value={curState.tool_state ?? []} onChange={(v) => updateState(curState.id, { tool_state: v })} />
                      </F>
                    </div>
                  )}
                  <div className="mt-3">
                    <F label="绑定话术 Canned Responses" hint="节点话术（schema 字段，v3.3.1 转移级生效）">
                      <MultiSelect options={cannedOptions} value={curState.canned_responses ?? []} onChange={(v) => updateState(curState.id, { canned_responses: v })} />
                    </F>
                  </div>
                  <div className="mt-3">
                    <F label="绑定检索器 Retrievers" hint="schema 字段（v3.3.1 引擎未消费，保留）">
                      <MultiSelect options={retrieverOptions} value={curState.retrievers ?? []} onChange={(v) => updateState(curState.id, { retrievers: v })} />
                    </F>
                  </div>
                  <div className="mt-3">
                    <F label="变量更新（进入/离开）" hint="schema 字段；v3.3.1 生效靠 tool_state 里的 variable_update 工具">
                      <TextInput rows={2} mono value={(curState.variable_updates_on_enter ?? []).map((x) => JSON.stringify(x)).join('\n')} onChange={(v) => updateState(curState.id, { variable_updates_on_enter: v.split('\n').filter(Boolean).map((s) => { try { return JSON.parse(s) } catch { return s } }) })} />
                    </F>
                  </div>
                  <div className="mt-4">
                    <div className="mb-2 border-b border-[var(--line)] pb-1.5 text-[11px] font-semibold text-[var(--ink-2)]">下一状态（转移）Transitions</div>
                    <div className="flex flex-col gap-2">
                      {(curState.transitions ?? []).map((t, i) => {
                        const setTr = (patch: Record<string, unknown>) => {
                          const tr = [...(curState.transitions ?? [])]
                          tr[i] = { ...tr[i], ...patch }
                          updateState(curState.id, { transitions: tr })
                        }
                        return (
                          <div key={i} className="rounded-md border border-[var(--line)] bg-[#FBFBFC] p-2.5">
                            <div className="flex items-center gap-2">
                              <span className="w-[64px] flex-none whitespace-nowrap text-[11.5px] text-[var(--ink-2)]">当条件</span>
                              <input className="h-7 min-w-0 flex-1 rounded-md border border-[var(--line-strong)] px-2 text-[11.5px] outline-none" placeholder="转移条件，如：用户选择一个合同后" value={t.condition ?? ''} onChange={(e) => setTr({ condition: e.target.value })} />
                            </div>
                            <div className="mt-1.5 flex items-center gap-2">
                              <span className="w-[64px] flex-none whitespace-nowrap text-[11.5px] text-[var(--ink-2)]">→ 到状态</span>
                              <Select className="min-w-0" value={t.to ?? ''} onChange={(v) => setTr({ to: v })} options={nextStateOptions} />
                              <button className="cursor-pointer text-[12px] text-[var(--muted)] hover:text-[var(--danger)]" onClick={() => updateState(curState.id, { transitions: (curState.transitions ?? []).filter((_, j) => j !== i) })}>✕</button>
                            </div>
                            <div className="mt-2">
                              <F label="绑定话术 Canned Responses" hint="转移命中时强制话术（SDK 支持，生效）">
                                <MultiSelect options={cannedOptions} value={t.canned_responses ?? []} onChange={(v) => setTr({ canned_responses: v })} />
                              </F>
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-3">
                              <label className="flex items-center gap-1.5 whitespace-nowrap text-[11.5px] text-[var(--ink-2)]">
                                超时分支
                                <Switch checked={t.timeout_branch ?? false} onChange={(v) => setTr({ timeout_branch: v })} />
                              </label>
                              <div className="flex items-center gap-1.5 whitespace-nowrap text-[11.5px] text-[var(--ink-2)]">
                                响应模式
                                <Select className="w-[110px] flex-none" value={t.response_mode ?? 'inherit'} onChange={(v) => setTr({ response_mode: v })} options={[{ value: 'inherit', label: 'inherit' }, { value: 'compose', label: 'compose' }, { value: 'strict', label: 'strict' }, { value: 'loose', label: 'loose' }]} />
                              </div>
                              <span className="text-[10.5px] text-[var(--muted)]">关键词（schema）</span>
                            </div>
                            <div className="mt-1 text-[10.5px] leading-relaxed text-[var(--muted)]">
                              响应模式 / 超时分支 / 关键词 为 schema 字段（v3.3.1 引擎未消费，仅随定义保存）
                            </div>
                            <div className="mt-1.5">
                              <ChipsInput value={t.keywords ?? []} onChange={(v) => setTr({ keywords: v })} placeholder="关键词（schema，回车添加）" />
                            </div>
                          </div>
                        )
                      })}
                      <button className="inline-flex h-7 cursor-pointer items-center justify-center rounded-md border border-dashed border-[var(--line-strong)] text-[11.5px] text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={() => updateState(curState.id, { transitions: [...(curState.transitions ?? []), { condition: '', to: '' }] })}>＋ 添加下一状态</button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="px-6 py-20 text-center text-[12.5px] text-[var(--muted)]">选择左侧节点进行编辑（或切换"流程图"查看整体）</div>
              )}
            </div>
          ) : (
            /* -------- 流程图（展示 + 校验） -------- */
            <GraphView journey={journey} selectedId={selectedId} onPick={(id) => { setSelected(id); setView('form') }} />
          )}
        </div>
      </div>
    </div>
  )
}

function stateOfTitle(id: string | undefined, states: JourneyStateDef[]): string {
  return states.find((s) => s.id === id)?.title ?? id ?? '—'
}

/** 流程图：层叠布局 + SVG 连线（只读展示 + 校验）。 */
function GraphView(props: { journey: JourneyDef; selectedId: string | null; onPick: (id: string) => void }) {
  const { journey, selectedId, onPick } = props
  const containerRef = useRef<HTMLDivElement>(null)
  const nodeRefs = useRef(new Map<string, HTMLDivElement>())
  const [lines, setLines] = useState<{ x1: number; y1: number; x2: number; y2: number }[]>([])

  const layout = useMemo(() => {
    const pos = new Map<string, { layer: number; order: number }>()
    const layerOf = new Map<string, number>()
    const queue: string[] = []
    const entry = journey.entry_node
    if (entry) { layerOf.set(entry, 0); queue.push(entry) }
    const seen = new Set<string>([entry ?? ''])
    while (queue.length) {
      const id = queue.shift()!
      const st = journey.states?.find((s) => s.id === id)
      const layer = layerOf.get(id) ?? 0
      for (const t of st?.transitions ?? []) {
        if (t.to && !seen.has(t.to)) { seen.add(t.to); layerOf.set(t.to, layer + 1); queue.push(t.to) }
      }
    }
    let maxLayer = Math.max(0, ...layerOf.values())
    for (const s of journey.states ?? []) {
      if (!seen.has(s.id)) { maxLayer += 1; layerOf.set(s.id, maxLayer); seen.add(s.id) }
    }
    const orderOf = new Map<string, number>()
    const perLayer = new Map<number, number>()
    for (const s of journey.states ?? []) {
      const l = layerOf.get(s.id) ?? 0
      orderOf.set(s.id, perLayer.get(l) ?? 0)
      perLayer.set(l, (perLayer.get(l) ?? 0) + 1)
    }
    for (const id of layerOf.keys()) pos.set(id, { layer: layerOf.get(id)!, order: orderOf.get(id) ?? 0 })
    return pos
  }, [journey])

  useEffect(() => {
    const compute = () => {
      const c = containerRef.current
      if (!c) return
      const crect = c.getBoundingClientRect()
      const out: typeof lines = []
      for (const s of journey.states ?? []) {
        const from = nodeRefs.current.get(s.id)
        if (!from) continue
        for (const t of s.transitions ?? []) {
          if (!t.to) continue
          const to = nodeRefs.current.get(t.to)
          if (!to) continue
          const fr = from.getBoundingClientRect()
          const tr = to.getBoundingClientRect()
          out.push({ x1: fr.right - crect.left, y1: fr.top + fr.height / 2 - crect.top, x2: tr.left - crect.left, y2: tr.top + tr.height / 2 - crect.top })
        }
      }
      setLines(out)
    }
    compute()
    const t = setTimeout(compute, 50)
    window.addEventListener('resize', compute)
    return () => { clearTimeout(t); window.removeEventListener('resize', compute) }
  }, [journey, layout])

  const warnings: string[] = []
  if (!journey.entry_node) warnings.push('缺少入口节点（entry_node）')
  for (const s of journey.states ?? []) {
    if (s.type !== 'end' && (s.transitions ?? []).length === 0) warnings.push(`「${s.title}」无出边（可能为死节点，若为终态请设 type=end）`)
    if (s.type === 'end' && (s.transitions ?? []).length > 0) warnings.push(`终态「${s.title}」不应有出边`)
  }

  const layers = [...new Set([...layout.values()].map((p) => p.layer))].sort((a, b) => a - b)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {warnings.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b border-[var(--line)] bg-[var(--warning-weak)] px-4 py-2">
          {warnings.map((w, i) => (
            <span key={i} className="rounded bg-white/60 px-1.5 py-0.5 text-[10.5px] text-[var(--warning)]">{w}</span>
          ))}
        </div>
      )}
      <div ref={containerRef} className="relative flex-1 overflow-auto bg-[var(--bg)] p-6" style={{ backgroundImage: 'radial-gradient(circle, #E4E7EC 1px, transparent 1px)', backgroundSize: '20px 20px' }}>
        <svg className="pointer-events-none absolute inset-0 h-full w-full">
          {lines.map((l, i) => (
            <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="#CBD2DC" strokeWidth="1.5" strokeDasharray="4 3" />
          ))}
        </svg>
        <div className="relative mx-auto flex max-w-[1000px] gap-10">
          {layers.map((layer) => (
            <div key={layer} className="flex min-w-[170px] flex-1 flex-col gap-4">
              {journey.states?.filter((s) => layout.get(s.id)?.layer === layer).map((s) => {
                const color = NODE_COLOR[s.type] ?? NODE_COLOR.chat
                return (
                  <div
                    key={s.id}
                    ref={(el) => { if (el) nodeRefs.current.set(s.id, el) }}
                    className={`cursor-pointer rounded-lg border p-3 ${selectedId === s.id ? 'border-[var(--primary)] shadow-[0_0_0_3px_var(--primary-weak)]' : 'border-[var(--line)]'}`}
                    style={{ background: color.bg }}
                    onClick={() => onPick(s.id)}
                  >
                    <div className="flex items-center gap-1">
                      <span className="rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase" style={{ background: color.text, color: '#fff' }}>{s.type}</span>
                      {s.id === journey.entry_node && <span className="rounded bg-[#1E293B] px-1 py-0.5 text-[8.5px] font-bold text-white">ENTRY</span>}
                      <span className="mono ml-auto text-[9px] text-[var(--muted)]">{s.id.slice(0, 6)}</span>
                    </div>
                    <div className="mt-1 text-[12px] font-semibold" style={{ color: color.text }}>{s.title}</div>
                    <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-[var(--ink-2)]">{(s.chat_state || s.tool_instruction || s.description) || ''}</div>
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
