/** 旅程：顶部可收缩「基本信息」+ 左侧状态列表 + 右侧表单编辑/流程图展示。 */
import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import type { JourneyDef, JourneyStateDef, JourneyTransitionDef } from '../../api/agentDefinition'
import { journeyLayoutsApi, type AnchorSide, type EdgeAnchors, type NodePos } from '../../api/client'
import { useBuild } from '../../store/build'
import { ChevronDown } from '../../components/Icons'
import { ChipsInput, F, MultiSelect, Select, Switch, TextInput } from './fields'

const NODE_COLOR: Record<string, { bg: string; text: string }> = {
  chat: { bg: '#EEF2FF', text: '#4F46E5' },
  tool: { bg: '#ECFDF5', text: '#059669' },
  fork: { bg: '#FFFBEB', text: '#B45309' },
}
const gid = (p: string) => `${p}_${Math.random().toString(36).slice(2, 8)}`
/** 查重重抽：与现有 id 冲突则重抽（Math.random 不保证唯一，撞号会导致引擎静默覆盖状态节点） */
const uniqueGid = (p: string, existing: Iterable<string>) => {
  const taken = new Set(existing)
  let id = gid(p)
  while (taken.has(id)) id = gid(p)
  return id
}

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
  const { definition, update, selectedId, setSelected, agentId } = useBuild()
  const [journeyId, setJourneyId] = useState<string | null>(null)
  const [view, setView] = useState<'form' | 'graph'>('form')
  const [infoOpen, setInfoOpen] = useState(false)
  const [stateFilter, setStateFilter] = useState('')
  // 全定义已占用 id（旅程 + 全部状态节点），新建时查重重抽，防跨旅程/节点撞号
  const takenIds = useMemo(
    () => new Set((definition?.journeys?.journeys ?? []).flatMap((j) => [j.id, ...(j.states ?? []).map((s) => s.id)])),
    [definition],
  )
  // 全定义已占用的转移 id：新建转移时自动赋 id（锚点键稳定的前提）
  const takenTrIds = useMemo(
    () => (definition?.journeys?.journeys ?? []).flatMap((j) => (j.states ?? []).flatMap((s) => (s.transitions ?? []).map((t) => t.transition_id ?? ''))),
    [definition],
  )
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
    const id = uniqueGid('jny', takenIds)
    const entry = uniqueGid('sta', takenIds)
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

  // 状态筛选（id / 名称，大小写不敏感）
  const filterQ = stateFilter.trim().toLowerCase()
  const filteredStates = filterQ
    ? states.filter((s) => s.id.toLowerCase().includes(filterQ) || (s.title ?? '').toLowerCase().includes(filterQ))
    : states

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
            状态（{filteredStates.length}{filterQ ? ` / ${states.length}` : ''}）
            <button className="ml-auto cursor-pointer text-[11px] font-normal text-[var(--primary)]" onClick={() => { const id = uniqueGid('sta', takenIds); update((d) => { const j = d.journeys!.journeys.find((x) => x.id === journey.id); j?.states?.push({ id, title: '新节点', type: 'chat', chat_state: '', transitions: [] }) }); setSelected(id) }}>＋ 新建节点</button>
          </div>
          <div className="px-2 pb-1.5">
            <div className="relative">
              <svg className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[var(--muted)]" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
              <input
                className="h-7 w-full rounded-md border border-[var(--line-strong)] bg-[var(--bg)] pl-7 pr-6 text-[11.5px] outline-none focus:border-[var(--primary-line)]"
                placeholder="筛选 id / 名称"
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value)}
              />
              {filterQ && (
                <button className="absolute right-1.5 top-1/2 -translate-y-1/2 cursor-pointer text-[12px] text-[var(--muted)] hover:text-[var(--ink)]" title="清空筛选" onClick={() => setStateFilter('')}>✕</button>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-2">
            {filteredStates.length === 0 && <div className="px-3 py-6 text-center text-[11.5px] text-[var(--muted)]">无匹配状态</div>}
            {filteredStates.map((s) => {
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
                <div className="p-5">
                  <div className="mb-4 flex items-center gap-2">
                    <span className="text-[13px] font-semibold">编辑节点</span>
                    <span className="mono text-[10.5px] text-[var(--muted)]">{curState.id}</span>
                    <button className="ml-auto cursor-pointer text-[12px] text-[var(--danger)]" onClick={() => { update((d) => { const j = d.journeys!.journeys.find((x) => x.id === journey.id); j!.states = j!.states!.filter((s) => s.id !== curState.id) }); setSelected(null) }}>删除节点</button>
                  </div>
                  {/* 左右两栏 6:4：左=节点属性，右=转移配置 */}
                  <div className="grid grid-cols-[3fr_2fr] gap-5 max-lg:grid-cols-1">
                    <div className="min-w-0">
                  <F label="标题"><TextInput value={curState.title} onChange={(v) => updateState(curState.id, { title: v })} /></F>
                  <div className="mt-3">
                    <F label="节点类型">
                      <Select value={curState.type} onChange={(v) => updateState(curState.id, { type: v as JourneyStateDef['type'] })} options={[{ value: 'chat', label: 'chat 对话' }, { value: 'tool', label: 'tool 工具' }, { value: 'fork', label: 'fork 分支' }]} />
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
                    </div>
                    <div className="min-w-0">
                  <div>
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
                      <button className="inline-flex h-7 cursor-pointer items-center justify-center rounded-md border border-dashed border-[var(--line-strong)] text-[11.5px] text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={() => updateState(curState.id, { transitions: [...(curState.transitions ?? []), { transition_id: uniqueGid('tr', takenTrIds), condition: '', to: '' }] })}>＋ 添加下一状态</button>
                    </div>
                  </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="px-6 py-20 text-center text-[12.5px] text-[var(--muted)]">选择左侧节点进行编辑（或切换"流程图"查看整体）</div>
              )}
            </div>
          ) : (
            /* -------- 流程图（展示 + 校验） -------- */
            <GraphView journey={journey} agentId={agentId} selectedId={selectedId} onPick={(id) => { setSelected(id); setView('form') }} />
          )}
        </div>
      </div>
    </div>
  )
}

function stateOfTitle(id: string | undefined, states: JourneyStateDef[]): string {
  return states.find((s) => s.id === id)?.title ?? id ?? '—'
}

const NODE_W = 190
const NODE_H = 116
const GAP_X = 84
const GAP_Y = 24
const EDGE_COLOR = '#8B96A5'

/** 锚点 = 节点方块四条边的中点；法线 = 该边朝外方向（贝塞尔控制点沿法线拉出）。 */
const SIDES: AnchorSide[] = ['top', 'right', 'bottom', 'left']
const SIDE_MID: Record<AnchorSide, (x: number, y: number) => { x: number; y: number }> = {
  top: (x, y) => ({ x: x + NODE_W / 2, y }),
  right: (x, y) => ({ x: x + NODE_W, y: y + NODE_H / 2 }),
  bottom: (x, y) => ({ x: x + NODE_W / 2, y: y + NODE_H }),
  left: (x, y) => ({ x, y: y + NODE_H / 2 }),
}
const SIDE_NORMAL: Record<AnchorSide, [number, number]> = { top: [0, -1], right: [1, 0], bottom: [0, 1], left: [-1, 0] }
const SIDE_LABEL: Record<AnchorSide, string> = { top: '上', right: '右', bottom: '下', left: '左' }

type Pos = { x: number; y: number }

/** 连线锚点键：transition_id → condition → 组内序号兜底（与 runtime journey_labels 同款回退）。 */
const trKey = (t: JourneyTransitionDef, i: number) => t.transition_id || t.condition || `#${i}`

/** 锚点键分隔符（|）：from/trKey 拼键用。state/transition id 不含 |；condition 含 | 为极小概率碰撞（后果=两线共享锚点配置）。勿用 NUL——MongoDB 键名禁止 NUL 字节。 */
const KEY_SEP = '|'

/** 自动锚点：目标在右 = 右→左前向边；目标在左 = 下→下绕行（同改造前的回边视觉）。 */
const autoAnchors = (a: Pos, b: Pos): { from: AnchorSide; to: AnchorSide } =>
  b.x >= a.x + NODE_W ? { from: 'right', to: 'left' } : { from: 'bottom', to: 'bottom' }

/** 挂载点坐标：side 边中点，沿边方向按 off（平行边错开量）平移。 */
function sidePoint(p: Pos, side: AnchorSide, off: number): Pos {
  const base = SIDE_MID[side](p.x, p.y)
  return side === 'top' || side === 'bottom' ? { x: base.x + off, y: base.y } : { x: base.x, y: base.y + off }
}

/** 任意锚点组合的贝塞尔路径：控制点沿两端法线拉出，距离随两端间距自适应。 */
function bezierPath(a: Pos, sideA: AnchorSide, offA: number, b: Pos, sideB: AnchorSide, offB: number): string {
  const q1 = sidePoint(a, sideA, offA)
  const q2 = sidePoint(b, sideB, offB)
  const n1 = SIDE_NORMAL[sideA]
  const n2 = SIDE_NORMAL[sideB]
  const d = Math.max(40, Math.min(120, Math.hypot(q2.x - q1.x, q2.y - q1.y) * 0.45))
  const c1 = { x: q1.x + n1[0] * d, y: q1.y + n1[1] * d }
  const c2 = { x: q2.x + n2[0] * d, y: q2.y + n2[1] * d }
  return `M ${q1.x} ${q1.y} C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${q2.x} ${q2.y}`
}

/**
 * 流程图：BFS 分层 + barycenter 降交叉布局；节点可拖拽、贝塞尔曲线连线、hover 高亮关联边。
 * 连线挂载点（anchor）可手调：点选连线 → 两端节点浮现四边中点圆点 → 点选切换挂载边（再点恢复自动）。
 * 锚点配置持久化到 server 独立集合（journey_layouts），与 Agent 定义层解耦——不脏草稿、不进版本 diff。
 */
function GraphView(props: { journey: JourneyDef; agentId: string | null; selectedId: string | null; onPick: (id: string) => void }) {
  const { journey, agentId, selectedId, onPick } = props
  const [hoverId, setHoverId] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [positions, setPositions] = useState<Map<string, { x: number; y: number }>>(new Map())
  const drag = useRef<{ id: string; startX: number; startY: number; ox: number; oy: number; moved: boolean } | null>(null)
  // 连线锚点：键 = "<from>|<transition_key>"，值 = 两端显式挂载边（缺省 = 自动）
  const [anchors, setAnchors] = useState<Record<string, EdgeAnchors>>({})
  // 节点拖拽落点（左上角坐标，partial 覆盖自动布局；未拖过的节点不在其中）
  const [nodePos, setNodePos] = useState<Record<string, NodePos>>({})
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null)

  // 分层 + barycenter 排序 → 初始布局（左→右分层，同层按前驱/后继平均位置排序降交叉）
  const layout = useMemo(() => {
    const layerOf = new Map<string, number>()
    const entry = journey.entry_node
    const queue: string[] = []
    if (entry) { layerOf.set(entry, 0); queue.push(entry) }
    const seen = new Set<string>(entry ? [entry] : [])
    while (queue.length) {
      const id = queue.shift()!
      const st = journey.states?.find((s) => s.id === id)
      const layer = layerOf.get(id) ?? 0
      for (const t of st?.transitions ?? []) {
        if (t.to && !seen.has(t.to)) { seen.add(t.to); layerOf.set(t.to, layer + 1); queue.push(t.to) }
      }
    }
    let maxLayer = Math.max(0, ...layerOf.values())
    for (const s of journey.states ?? []) if (!seen.has(s.id)) { maxLayer += 1; layerOf.set(s.id, maxLayer); seen.add(s.id) }

    const orderOf = new Map<string, number>()
    const sweep = (dir: 1 | -1) => {
      const byLayer = new Map<number, string[]>()
      for (const s of journey.states ?? []) {
        const l = layerOf.get(s.id) ?? 0
        byLayer.set(l, [...(byLayer.get(l) ?? []), s.id])
      }
      for (const l of [...byLayer.keys()].sort((a, b) => (dir === 1 ? a - b : b - a))) {
        const ids = byLayer.get(l)!
        const bary = new Map<string, number>()
        for (const id of ids) {
          const st = journey.states?.find((s) => s.id === id)
          const nbs = dir === 1
            ? (st?.transitions ?? []).map((t) => t.to).filter((x): x is string => !!x && layerOf.get(x) === l + 1)
            : (journey.states ?? []).filter((s) => (s.transitions ?? []).some((t) => t.to === id && layerOf.get(s.id) === l - 1)).map((s) => s.id)
          const vals = nbs.map((n) => orderOf.get(n)).filter((v): v is number => v !== undefined)
          bary.set(id, vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : Infinity)
        }
        ids.sort((a, b) => (bary.get(a) ?? Infinity) - (bary.get(b) ?? Infinity))
        ids.forEach((id, i) => orderOf.set(id, i))
      }
    }
    sweep(1); sweep(-1); sweep(1)

    const pos = new Map<string, { x: number; y: number }>()
    for (const s of journey.states ?? []) {
      const l = layerOf.get(s.id) ?? 0
      const o = orderOf.get(s.id) ?? 0
      pos.set(s.id, { x: l * (NODE_W + GAP_X), y: o * (NODE_H + GAP_Y) })
    }
    return pos
  }, [journey])

  // 旅程变化时重置布局：自动布局 + 已持久化的拖拽落点覆盖（未拖过的节点走自动位置）
  const layoutKey = JSON.stringify([...layout].sort())
  useEffect(() => {
    setPositions(new Map([...layout].map(([id, p]) => [id, nodePos[id] ?? p])))
  }, [layoutKey, nodePos]) // eslint-disable-line react-hooks/exhaustive-deps

  // 边：逐条转移（锚点按 transition 定位）；同 from→to 的平行边按组内序号错开
  const edges = useMemo(() => {
    const raw: { key: string; from: string; to: string; gi: number; pair: string }[] = []
    const nOf = new Map<string, number>()
    const giOf = new Map<string, number>()
    for (const s of journey.states ?? []) {
      for (const [i, t] of (s.transitions ?? []).entries()) {
        if (!t.to) continue
        const pair = `${s.id}${KEY_SEP}${t.to}`
        nOf.set(pair, (nOf.get(pair) ?? 0) + 1)
        const gi = giOf.get(pair) ?? 0
        giOf.set(pair, gi + 1)
        raw.push({ key: `${s.id}${KEY_SEP}${trKey(t, i)}`, from: s.id, to: t.to, gi, pair })
      }
    }
    return raw.map((e) => ({ ...e, sep: (e.gi - ((nOf.get(e.pair) ?? 1) - 1) / 2) * 14 }))
  }, [journey])

  // ---------- 布局（锚点 + 节点坐标）：加载 / 保存（与定义层解耦，调整即自动持久化，不脏草稿） ----------
  const validEdgeKeys = useMemo(() => new Set(edges.map((e) => e.key)), [edges])
  const validStateIds = useMemo(() => new Set((journey.states ?? []).map((s) => s.id)), [journey])

  useEffect(() => {
    if (!agentId) return
    let alive = true
    setSelectedEdge(null)
    setAnchors({})
    setNodePos({})
    journeyLayoutsApi
      .get(agentId, journey.id)
      .then((doc) => {
        if (!alive) return
        setAnchors(doc.edges ?? {})
        setNodePos(doc.nodes ?? {})
      })
      .catch(() => { /* 布局拉取失败静默：全部回落自动布局/自动锚点 */ })
    return () => {
      alive = false
    }
  }, [agentId, journey.id])

  // Esc 取消连线选中
  useEffect(() => {
    if (!selectedEdge) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedEdge(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedEdge])

  /** 全量持久化布局：清理两类的孤儿键（删节点/删转移后的残留），本地状态与服务端同步替换。 */
  const persistLayout = (nextEdges: Record<string, EdgeAnchors>, nextNodes: Record<string, NodePos>) => {
    if (!agentId) return
    const prunedEdges = Object.fromEntries(Object.entries(nextEdges).filter(([k]) => validEdgeKeys.has(k)))
    const prunedNodes = Object.fromEntries(Object.entries(nextNodes).filter(([k]) => validStateIds.has(k)))
    setAnchors(prunedEdges)
    setNodePos(prunedNodes)
    journeyLayoutsApi.save(agentId, journey.id, { edges: prunedEdges, nodes: prunedNodes }).catch(() => { /* 保存失败静默，下次变更再存 */ })
  }

  /** 设置/切换某端挂载点；传 null 清除该端（恢复自动）。 */
  const setAnchor = (key: string, end: 'from' | 'to', side: AnchorSide | null) => {
    const field: keyof EdgeAnchors = end === 'from' ? 'from_anchor' : 'to_anchor'
    const cur: EdgeAnchors = { ...(anchors[key] ?? {}) }
    if (side === null) delete cur[field]
    else cur[field] = side
    const next = { ...anchors }
    if (Object.keys(cur).length === 0) delete next[key]
    else next[key] = cur
    persistLayout(next, nodePos)
  }

  /** 恢复自动：清除该连线两端的显式锚点。 */
  const clearAnchors = (key: string) => {
    if (!anchors[key]) return
    const next = { ...anchors }
    delete next[key]
    persistLayout(next, nodePos)
  }

  // 贝塞尔曲线路径：显式锚点优先，缺省按几何关系自动（前向 右→左；回边 下→下绕行）
  const paths = useMemo(
    () =>
      edges
        .map((e) => {
          const a = positions.get(e.from)
          const b = positions.get(e.to)
          if (!a || !b) return null
          const auto = autoAnchors(a, b)
          const saved = anchors[e.key]
          const d = bezierPath(a, saved?.from_anchor ?? auto.from, e.sep, b, saved?.to_anchor ?? auto.to, e.sep)
          return { key: e.key, from: e.from, to: e.to, d }
        })
        .filter((p): p is NonNullable<typeof p> => p !== null),
    [edges, positions, anchors]
  )

  const contentW = (positions.size ? Math.max(...[...positions.values()].map((p) => p.x + NODE_W)) : NODE_W) + 24
  const contentH = (positions.size ? Math.max(...[...positions.values()].map((p) => p.y + NODE_H)) : NODE_H) + 24

  const startDrag = (e: ReactPointerEvent<HTMLDivElement>, id: string) => {
    const cur = positions.get(id)
    if (!cur) return
    e.currentTarget.setPointerCapture?.(e.pointerId)
    drag.current = { id, startX: e.clientX, startY: e.clientY, ox: cur.x, oy: cur.y, moved: false }
  }
  const moveDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    if (!d.moved && Math.hypot(dx, dy) > 4) d.moved = true
    if (!d.moved) return
    setDragId(d.id)
    setPositions((prev) => {
      const next = new Map(prev)
      next.set(d.id, { x: Math.max(0, d.ox + dx), y: Math.max(0, d.oy + dy) })
      return next
    })
  }
  const endDrag = (e: ReactPointerEvent<HTMLDivElement>, id: string) => {
    const d = drag.current
    drag.current = null
    setDragId(null)
    try { e.currentTarget.releasePointerCapture?.(e.pointerId) } catch { /* noop */ }
    if (!d) return
    if (!d.moved) {
      onPick(id) // 未拖拽 = 点击 → 进入编辑（拖拽的键盘/点击备选）
      return
    }
    // 拖拽结束：把该节点的落点（左上角坐标）持久化到布局（未拖过的节点仍走自动布局）
    const cur = positions.get(id)
    if (cur) persistLayout(anchors, { ...nodePos, [id]: { x: cur.x, y: cur.y } })
  }

  const warnings: string[] = []
  if (!journey.entry_node) warnings.push('缺少入口节点（entry_node）')
  for (const s of journey.states ?? []) {
    for (const t of s.transitions ?? []) {
      if (t.to && !journey.states?.some((x) => x.id === t.to)) warnings.push(`「${s.title}」的出边指向不存在的状态 ${t.to}`)
    }
  }

  // 当前选中的连线（锚点圆点挂在它的两端节点上）
  const selEdge = selectedEdge ? (edges.find((e) => e.key === selectedEdge) ?? null) : null

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {warnings.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b border-[var(--line)] bg-[var(--warning-weak)] px-4 py-2">
          {warnings.map((w, i) => (
            <span key={i} className="rounded bg-white/60 px-1.5 py-0.5 text-[10.5px] text-[var(--warning)]">{w}</span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-2 border-b border-[var(--line)] px-4 py-1.5">
        {selEdge ? (
          <>
            <span className="text-[11px] text-[var(--primary)]">
              已选连线：{stateOfTitle(selEdge.from, journey.states ?? [])} → {stateOfTitle(selEdge.to, journey.states ?? [])}
              　点两端节点的边中点圆点调整挂载（再点同一圆点恢复自动）· Esc/点空白取消
            </span>
            <button
              className="inline-flex h-7 cursor-pointer items-center rounded-md border border-[var(--line-strong)] px-2.5 text-[11.5px] text-[var(--ink-2)] hover:bg-[#F1F5F9]"
              onClick={() => clearAnchors(selEdge.key)}
            >恢复自动</button>
          </>
        ) : (
          <span className="text-[11px] text-[var(--muted)]">拖拽节点调整布局（自动保存）· 点击节点编辑 · 点击连线调整挂载点 · hover 高亮关联边</span>
        )}
        <button
          className="ml-auto inline-flex h-7 cursor-pointer items-center gap-1 rounded-md border border-[var(--line-strong)] px-2.5 text-[11.5px] text-[var(--ink-2)] hover:bg-[#F1F5F9]"
          title="节点位置回到自动布局（清空已保存的拖拽坐标；连线挂载点保留）"
          onClick={() => { persistLayout(anchors, {}); setPositions(new Map(layout)) }}
        >重置布局</button>
      </div>
      <div className="relative flex-1 overflow-auto bg-[var(--bg)] p-6" style={{ backgroundImage: 'radial-gradient(circle, #E4E7EC 1px, transparent 1px)', backgroundSize: '20px 20px' }}>
        <div className="relative" style={{ width: contentW, height: contentH }} onPointerDown={(e) => { if (e.target === e.currentTarget) setSelectedEdge(null) }}>
          {/* 连线：置于节点下层，hover 时节点不被遮挡；透明宽命中区支持点选 */}
          <svg className="pointer-events-none absolute inset-0" width={contentW} height={contentH}>
            <defs>
              <marker id="pa-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill={EDGE_COLOR} />
              </marker>
              <marker id="pa-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--primary)" />
              </marker>
            </defs>
            {paths.map((l) => {
              const active = hoverId !== null && (l.from === hoverId || l.to === hoverId)
              const isSel = selectedEdge === l.key
              return (
                <g key={l.key}>
                  <path
                    d={l.d}
                    fill="none"
                    stroke="#000"
                    strokeOpacity={0}
                    strokeWidth={12}
                    style={{ pointerEvents: 'stroke', cursor: 'pointer' }}
                    onClick={(e) => { e.stopPropagation(); setSelectedEdge(l.key) }}
                  />
                  <path
                    d={l.d}
                    fill="none"
                    stroke={isSel ? 'var(--primary)' : active ? 'var(--primary)' : EDGE_COLOR}
                    strokeWidth={isSel || active ? 2 : 1.5}
                    strokeDasharray={isSel ? undefined : '4 3'}
                    strokeOpacity={hoverId === null || active || isSel ? 1 : 0.25}
                    markerEnd={isSel ? 'url(#pa-arrow-on)' : 'url(#pa-arrow)'}
                  />
                </g>
              )
            })}
          </svg>
          {journey.states?.map((s) => {
            const p = positions.get(s.id)
            if (!p) return null
            const color = NODE_COLOR[s.type] ?? NODE_COLOR.chat
            const dragging = dragId === s.id
            return (
              <div
                key={s.id}
                className={`absolute rounded-lg border p-3 transition-shadow ${selectedId === s.id ? 'border-[var(--primary)] shadow-[0_0_0_3px_var(--primary-weak)]' : 'border-[var(--line)]'} ${dragging ? 'cursor-grabbing shadow-lg' : 'cursor-grab hover:shadow-md'}`}
                style={{ left: p.x, top: p.y, width: NODE_W, height: NODE_H, background: color.bg, touchAction: 'none' }}
                onPointerDown={(e) => startDrag(e, s.id)}
                onPointerMove={moveDrag}
                onPointerUp={(e) => endDrag(e, s.id)}
                onMouseEnter={() => setHoverId(s.id)}
                onMouseLeave={() => setHoverId((h) => (h === s.id ? null : h))}
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
          {/* 选中连线的锚点圆点：两端节点各 4 个边中点，点击切换挂载边（再点恢复自动） */}
          {selEdge && (() => {
            const a = positions.get(selEdge.from)
            const b = positions.get(selEdge.to)
            if (!a || !b) return null
            const auto = autoAnchors(a, b)
            const saved = anchors[selEdge.key] ?? {}
            const dots = (p: Pos, end: 'from' | 'to', explicit: AnchorSide | undefined, effective: AnchorSide) =>
              SIDES.map((side) => {
                const pt = SIDE_MID[side](p.x, p.y)
                const active = effective === side
                return (
                  <button
                    key={`${end}-${side}`}
                    title={`${end === 'from' ? '源端' : '目标端'}挂载到${SIDE_LABEL[side]}边中点${explicit === side ? '（当前挂载，点击恢复自动）' : ''}`}
                    className="absolute z-20 grid h-[18px] w-[18px] -translate-x-1/2 -translate-y-1/2 cursor-pointer place-items-center rounded-full border-2 bg-white shadow-sm"
                    style={{ left: pt.x, top: pt.y, borderColor: active ? 'var(--primary)' : '#C7CEDA' }}
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => { e.stopPropagation(); setAnchor(selEdge.key, end, explicit === side ? null : side) }}
                  >
                    <span className="h-[6px] w-[6px] rounded-full" style={{ background: active ? 'var(--primary)' : '#C7CEDA' }} />
                  </button>
                )
              })
            return (
              <>
                {dots(a, 'from', saved.from_anchor, saved.from_anchor ?? auto.from)}
                {dots(b, 'to', saved.to_anchor, saved.to_anchor ?? auto.to)}
              </>
            )
          })()}
        </div>
      </div>
    </div>
  )
}
