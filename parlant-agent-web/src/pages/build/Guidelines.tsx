/** 指南（master-detail）：左列表（条件→动作） + 右检查器。 */
import { useState } from 'react'
import type { GuidelineDef } from '../../api/agentDefinition'
import { useBuild } from '../../store/build'
import { F, MultiSelect, Section, Select, Switch, TextInput } from './fields'

const CRIT: Record<string, string> = { low: '低', medium: '中', high: '高' }

export default function Guidelines() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const [kw, setKw] = useState('')
  if (!definition) return null
  const list = definition.guidelines?.guidelines ?? []
  const shown = list.filter((g) => !kw || g.condition.includes(kw) || g.action.includes(kw))
  const cur = list.find((g) => g.id === selectedId) ?? null

  const upsert = (patch: Partial<GuidelineDef>) => {
    if (!cur) return
    update((d) => {
      const arr = d.guidelines!.guidelines
      const i = arr.findIndex((g) => g.id === cur.id)
      if (i >= 0) arr[i] = { ...arr[i], ...patch }
    })
  }

  return (
    <div className="flex min-h-0 flex-1">
      {/* 列表 */}
      <div className="flex w-[420px] flex-none flex-col border-r border-[var(--line)] bg-[var(--surface)]">
        <div className="flex items-center gap-2 border-b border-[var(--line)] p-3">
          <input className="h-7 flex-1 rounded-md border border-[var(--line-strong)] px-2 text-[12px] outline-none" placeholder="搜索条件 / 动作…" value={kw} onChange={(e) => setKw(e.target.value)} />
          <button className="inline-flex h-7 cursor-pointer items-center rounded-md bg-[var(--primary)] px-2.5 text-[11.5px] font-medium text-white" onClick={() => {
            const id = `gdl_${Math.random().toString(36).slice(2, 8)}`
            update((d) => d.guidelines!.guidelines.unshift({ id, condition: '', action: '', criticality: 'medium', priority: 1, enabled: true }))
            setSelected(id)
          }}>＋ 新建指南</button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {shown.map((g) => (
            <div key={g.id} className={`cursor-pointer border-b border-[var(--line)] p-3 ${g.id === selectedId ? 'bg-[var(--primary-weak)]' : 'hover:bg-[#FAFBFF]'}`} onClick={() => setSelected(g.id)}>
              <div className="line-clamp-2 text-[12.5px] font-medium leading-snug text-[var(--ink)]">{g.condition || '（空条件）'}</div>
              <div className="mt-1 line-clamp-2 text-[12px] leading-snug text-[var(--ink-2)]">
                <span className="mr-1 font-semibold text-[var(--primary)]">→</span>
                {g.action || '（空动作）'}
              </div>
              <div className="mt-1.5 flex items-center gap-1.5">
                <span className={`rounded px-1.5 text-[10.5px] ${g.criticality === 'high' ? 'bg-[#FEF2F2] text-[var(--danger)]' : g.criticality === 'medium' ? 'bg-[#F1F5F9] text-[var(--ink-2)]' : 'bg-[#F1F5F9] text-[var(--ink-2)]'}`}>{CRIT[g.criticality] ?? g.criticality}</span>
                <span className="mono text-[10.5px] text-[var(--muted)]">P{g.priority}</span>
                {g.enabled === false && <span className="rounded bg-[#F1F5F9] px-1.5 text-[10.5px] text-[var(--muted)]">停用</span>}
                {g.journey_ids?.map((j) => <span key={j} className="mono rounded bg-[#F5F3FF] px-1 text-[10px] text-[#6D28D9]">{j.slice(0, 8)}</span>)}
              </div>
            </div>
          ))}
          {!shown.length && <div className="px-4 py-12 text-center text-[12px] text-[var(--muted)]">无指南</div>}
        </div>
      </div>

      {/* 检查器 */}
      <div className="flex-1 overflow-y-auto bg-[var(--surface)]">
        {cur ? (
          <div className="p-5">
            <div className="mb-4 flex items-center gap-2">
              <span className="text-[13px] font-semibold">编辑指南</span>
              <span className="mono text-[10.5px] text-[var(--muted)]">{cur.id}</span>
              <button className="ml-auto cursor-pointer text-[12px] text-[var(--danger)]" onClick={() => {
                update((d) => (d.guidelines!.guidelines = d.guidelines!.guidelines.filter((g) => g.id !== cur.id)))
                setSelected(null)
              }}>删除</button>
            </div>
            <F label="条件 Condition" hint="LLM 评估的触发条件" full>
              <TextInput rows={3} value={cur.condition} onChange={(v) => upsert({ condition: v })} />
            </F>
            <div className="mt-4">
              <F label="动作 Action" hint="命中后要求智能体执行的行为" full>
                <TextInput rows={3} value={cur.action} onChange={(v) => upsert({ action: v })} />
              </F>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <F label="严重级别">
                <Select value={cur.criticality} onChange={(v) => upsert({ criticality: v as GuidelineDef['criticality'] })} options={[{ value: 'low', label: '低 low' }, { value: 'medium', label: '中 medium' }, { value: 'high', label: '高 high' }]} />
              </F>
              <F label="优先级" hint="数值越大越优先">
                <TextInput mono value={String(cur.priority)} onChange={(v) => upsert({ priority: Number(v) || 0 })} />
              </F>
            </div>
            <div className="mt-4 flex items-center gap-3">
              <span className="text-[12px] font-medium text-[var(--ink-2)]">启用</span>
              <Switch checked={cur.enabled !== false} onChange={(v) => upsert({ enabled: v })} />
            </div>
            <Section title="绑定（从已有组件选择）">
              <F label="预设话术 Canned Responses">
                <MultiSelect
                  options={(definition.canned_responses?.responses ?? []).map((c) => ({ value: c.id, label: c.template.slice(0, 40) }))}
                  value={cur.canned_responses ?? []}
                  onChange={(v) => upsert({ canned_responses: v })}
                />
              </F>
              <div className="mt-3">
                <F label="旅程 Journeys" hint="仅在这些旅程上下文中生效">
                  <MultiSelect
                    options={(definition.journeys?.journeys ?? []).map((j) => ({ value: j.id, label: j.title }))}
                    value={cur.journey_ids ?? []}
                    onChange={(v) => upsert({ journey_ids: v })}
                  />
                </F>
              </div>
              <div className="mt-3">
                <F label="旅程状态 Journey Nodes">
                  <MultiSelect
                    options={(definition.journeys?.journeys ?? []).flatMap((j) =>
                      (j.states ?? []).map((s) => ({ value: s.id, label: `${j.title} · ${s.title}` })),
                    )}
                    value={cur.node_ids ?? []}
                    onChange={(v) => upsert({ node_ids: v })}
                  />
                </F>
              </div>
              <div className="mt-3">
                <F label="工具 Tools">
                  <MultiSelect
                    options={(definition.tools?.tools ?? []).map((t) => ({ value: t.id ?? t.name, label: t.name }))}
                    value={cur.tools ?? []}
                    onChange={(v) => upsert({ tools: v })}
                  />
                </F>
              </div>
            </Section>
            <Section title="命中时更新变量">
              <div className="rounded-md border border-[var(--line)] bg-[#FBFBFC] p-2.5 text-[12px] text-[var(--ink-2)]">
                <span className="mono text-[11px] text-[var(--muted)]">variable_updates_on_match</span>
                <div className="mt-1">变量更新项（键=值）编辑：<span className="text-[var(--muted)]">本版以 JSON 高级编辑承载（后续增强）</span></div>
              </div>
            </Section>
          </div>
        ) : (
          <div className="px-6 py-20 text-center text-[12.5px] text-[var(--muted)]">选择左侧一条指南进行编辑</div>
        )}
      </div>
    </div>
  )
}
