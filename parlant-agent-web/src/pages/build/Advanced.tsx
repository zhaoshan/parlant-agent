/** 关系（完整编辑） + 观察（观察性指南）—— 高级模块。 */
import type { AgentDefinition, GuidelineDef, RelationshipDef } from '../../api/agentDefinition'
import { useBuild } from '../../store/build'
import { F, Select, Switch, TextInput, inputCls } from './fields'

/* ---------------- 关系 ---------------- */
// 与 runtime RelationshipDef（app/models/definition.py）+ loader _resolve_relationship_entity 对齐：
// source/target 是扁平字符串引用（指南/观察 id gdl_*/obs_*、旅程 id jny_* 或工具名），
// 运行时按 id 内容解析实体（Guideline / TAG_ALL / Tool），前端不再设"实体类型"下拉。
const KINDS = [
  { value: 'entailment', label: 'ENTAILMENT 蕴含' },
  { value: 'priority', label: 'PRIORITY 优先级' },
  { value: 'dependency', label: 'DEPENDENCY 依赖' },
  { value: 'dependency_any', label: 'DEPENDENCY_ANY 依赖任一' },
  { value: 'disambiguation', label: 'DISAMBIGUATION 消歧' },
  { value: 'reevaluation', label: 'REEVALUATION 重评估' },
  { value: 'overlap', label: 'OVERLAP 重叠' },
]

/** 由 id 前缀推断实体种类（仅展示用；运行时以 id 内容为准）。 */
function entityKindLabel(ref: string): string {
  if (!ref) return '未指定'
  if (/^(gdl|obs)_/.test(ref)) return 'Guideline'
  if (ref.startsWith('jny_')) return 'Journey'
  return 'Tool/其它'
}

/** 按引用 id/名 在定义内解析可读标签：指南/观察取 description（回退 condition）、旅程取 title、工具取 name。 */
function refLabel(ref: string, d: AgentDefinition | null | undefined): string {
  if (!ref) return ''
  const g = [...(d?.guidelines?.guidelines ?? []), ...(d?.observations?.observations ?? [])].find((x) => x.id === ref)
  if (g) return g.description?.trim() || g.condition?.trim() || ''
  const j = d?.journeys?.journeys.find((x) => x.id === ref)
  if (j) return j.title || ''
  const t = d?.tools?.tools.find((x) => x.name === ref)
  return t?.name ?? ''
}

const truncate = (s: string, n: number) => (s.length > n ? `${s.slice(0, n)}…` : s)

/** 构建源/目标实体下拉：按 指南/观察/旅程/工具 分组，选项显示「名称 (id)」。 */
function entityGroups(d: AgentDefinition | null | undefined): { label: string; options: { value: string; label: string }[] }[] {
  return [
    {
      label: 'Guidelines 指南',
      options: (d?.guidelines?.guidelines ?? []).map((g) => ({ value: g.id, label: `${truncate(refLabel(g.id, d), 20)} (${g.id})` })),
    },
    {
      label: 'Observations 观察',
      options: (d?.observations?.observations ?? []).map((o) => ({ value: o.id, label: `${truncate(refLabel(o.id, d), 20)} (${o.id})` })),
    },
    {
      label: 'Journeys 旅程',
      options: (d?.journeys?.journeys ?? []).map((j) => ({ value: j.id, label: `${j.title} (${j.id})` })),
    },
    {
      label: 'Tools 工具',
      options: (d?.tools?.tools ?? []).map((t) => ({ value: t.name, label: t.name })),
    },
  ]
}

function EntitySelect(props: { value: string; onChange: (v: string) => void; definition: AgentDefinition | null | undefined }) {
  const { value, onChange, definition } = props
  const groups = entityGroups(definition)
  const known = groups.some((g) => g.options.some((o) => o.value === value))
  return (
    <div className="flex flex-col gap-1">
      <select className={`${inputCls} w-full cursor-pointer`} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">（未选择）</option>
        {groups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.options.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </optgroup>
        ))}
      </select>
      {value && !known && (
        <div className="text-[11px] text-[var(--danger)]">「{value}」不在当前定义内（运行时可能无法解析该关系）</div>
      )}
    </div>
  )
}

export function Relationships() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const rows = definition?.relationships?.relationships ?? []
  const setRows = (fn: (a: RelationshipDef[]) => RelationshipDef[]) => update((d) => (d.relationships!.relationships = fn(d.relationships!.relationships ?? [])))
  const cur = rows.find((r) => r.id === selectedId) ?? null

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex w-[460px] flex-none flex-col border-r border-[var(--line)] bg-[var(--surface)]">
        <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2.5">
          <span className="text-[12.5px] font-semibold">关系</span>
          <span className="mono text-[11px] text-[var(--muted)]">{rows.length}</span>
          <button className="ml-auto inline-flex h-7 cursor-pointer items-center rounded-md bg-[var(--primary)] px-2.5 text-[11.5px] font-medium text-white" onClick={() => {
            const id = `rel_${Math.random().toString(36).slice(2, 8)}`
            setRows((a) => [...a, { id, source: '', kind: 'dependency', target: '' }])
            setSelected(id)
          }}>＋ 新建关系</button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {rows.map((r) => (
            <div key={r.id} className={`cursor-pointer border-b border-[var(--line)] px-3.5 py-3 ${r.id === selectedId ? 'bg-[var(--primary-weak)]' : 'hover:bg-[#FAFBFF]'}`} onClick={() => setSelected(r.id)}>
              <div className="flex items-center gap-1.5 text-[12px]">
                <span className="rounded bg-[#EEF2FF] px-1.5 py-0.5 text-[10px] font-medium text-[var(--primary)]">{r.kind}</span>
                <span className="mono min-w-0 flex-1 truncate text-[var(--ink)]" title={refLabel(r.source, definition)}>
                  {truncate(refLabel(r.source, definition), 16) || '未指定'}
                </span>
                <span className="shrink-0 text-[var(--muted)]">→</span>
                <span className="mono min-w-0 flex-1 truncate text-right text-[var(--ink)]" title={refLabel(r.target, definition)}>
                  {truncate(refLabel(r.target, definition), 16) || '未指定'}
                </span>
              </div>
              <div className="mono mt-0.5 flex items-center gap-2 text-[10px] text-[var(--muted)]">
                <span className="min-w-0 truncate" title={r.source}>{r.source}</span>
                <span className="shrink-0">{entityKindLabel(r.source)} → {entityKindLabel(r.target)} · {r.id}</span>
                <span className="min-w-0 truncate text-right" title={r.target}>{r.target}</span>
              </div>
            </div>
          ))}
          {!rows.length && <div className="px-4 py-14 text-center text-[12px] text-[var(--muted)]">暂无关系</div>}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto bg-[var(--surface)]">
        {cur ? (
          <div className="p-5">
            <div className="mb-4 flex items-center gap-2">
              <span className="text-[13px] font-semibold">编辑关系</span>
              <span className="mono text-[10.5px] text-[var(--muted)]">{cur.id}</span>
              <button className="ml-auto cursor-pointer text-[12px] text-[var(--danger)]" onClick={() => { setRows((a) => a.filter((r) => r.id !== cur.id)); setSelected(null) }}>删除</button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <F label="源实体" hint="本定义内的指南/观察/旅程/工具">
                <EntitySelect value={cur.source} onChange={(v) => setRows((a) => a.map((r) => r.id === cur.id ? { ...r, source: v } : r))} definition={definition} />
              </F>
              <F label="关系类型 Kind">
                <Select value={cur.kind.toLowerCase()} onChange={(v) => setRows((a) => a.map((r) => r.id === cur.id ? { ...r, kind: v } : r))} options={KINDS} />
              </F>
              <F label="目标实体" hint="本定义内的指南/观察/旅程/工具">
                <EntitySelect value={cur.target} onChange={(v) => setRows((a) => a.map((r) => r.id === cur.id ? { ...r, target: v } : r))} definition={definition} />
              </F>
              <div className="flex items-end pb-1 text-[11px] text-[var(--muted)]">
                {entityKindLabel(cur.source)} → {entityKindLabel(cur.target)}
              </div>
            </div>
            <div className="mt-4">
              <F label="触发说明" hint="该关系何时生效">
                <TextInput rows={2} value={cur.description ?? ''} onChange={(v) => setRows((a) => a.map((r) => r.id === cur.id ? { ...r, description: v } : r))} />
              </F>
            </div>
            <div className="mt-4 rounded-md border border-[var(--line)] bg-[#FBFBFC] p-2.5 text-[11.5px] leading-relaxed text-[var(--ink-2)]">
              <b className="text-[var(--ink)]">关系种类说明</b>（docs/02-concepts/08）：蕴含（说 A 即 B）、优先级（优先于）、依赖（依赖某实体）、消歧（消除歧义）。
            </div>
          </div>
        ) : (
          <div className="px-6 py-20 text-center text-[12.5px] text-[var(--muted)]">选择左侧一条关系进行编辑</div>
        )}
      </div>
    </div>
  )
}

/* ---------------- 观察（观察性指南） ---------------- */
export function Observations() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const rows = definition?.observations?.observations ?? []
  const setRows = (fn: (a: GuidelineDef[]) => GuidelineDef[]) => update((d) => (d.observations!.observations = fn(d.observations!.observations ?? [])))
  const cur = rows.find((o) => o.id === selectedId) ?? null
  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex w-[420px] flex-none flex-col border-r border-[var(--line)] bg-[var(--surface)]">
        <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2.5">
          <span className="text-[12.5px] font-semibold">观察（观察性指南）</span>
          <span className="mono text-[11px] text-[var(--muted)]">{rows.length}</span>
          <button className="ml-auto inline-flex h-7 cursor-pointer items-center rounded-md bg-[var(--primary)] px-2.5 text-[11.5px] font-medium text-white" onClick={() => {
            const id = `obs_${Math.random().toString(36).slice(2, 8)}`
            setRows((a) => [...a, { id, condition: '', action: '', criticality: 'medium', priority: 1, enabled: true }])
            setSelected(id)
          }}>＋ 新建观察</button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {rows.map((o) => (
            <div key={o.id} className={`cursor-pointer border-b border-[var(--line)] p-3 ${o.id === selectedId ? 'bg-[var(--primary-weak)]' : 'hover:bg-[#FAFBFF]'}`} onClick={() => setSelected(o.id)}>
              <div className="line-clamp-1 text-[12.5px] font-medium text-[var(--ink)]">{o.condition || '（空条件）'}</div>
              <div className="mt-0.5 line-clamp-1 text-[12px] text-[var(--ink-2)]"><span className="text-[var(--primary)]">→ </span>{o.action}</div>
            </div>
          ))}
          {!rows.length && <div className="px-4 py-14 text-center text-[12px] text-[var(--muted)]">暂无观察（观察性指南在事件流中触发）</div>}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto bg-[var(--surface)]">
        {cur ? (
          <div className="p-5">
            <div className="mb-4 flex items-center gap-2">
              <span className="text-[13px] font-semibold">编辑观察</span>
              <span className="mono text-[10.5px] text-[var(--muted)]">{cur.id}</span>
              <button className="ml-auto cursor-pointer text-[12px] text-[var(--danger)]" onClick={() => { setRows((a) => a.filter((o) => o.id !== cur.id)); setSelected(null) }}>删除</button>
            </div>
            <F label="观察条件 Condition" hint="对话/事件中观察到该状态时触发" full>
              <TextInput rows={2} value={cur.condition} onChange={(v) => setRows((a) => a.map((o) => o.id === cur.id ? { ...o, condition: v } : o))} />
            </F>
            <div className="mt-3 rounded-md border border-[var(--primary-line)] bg-[var(--primary-weak)] p-2.5 text-[11.5px] leading-relaxed text-[var(--primary)]">
              <b>观察性指南（Observational Guideline）</b>：由对话/事件中的"观察"触发，<b>没有 Action</b>——
              命中即标记该状态已发生，不要求智能体执行动作（参考 docs/02-concepts/04-指南Guidelines.md）。
            </div>
            <div className="mt-3 grid grid-cols-2 gap-4">
              <F label="严重级别">
                <Select value={cur.criticality} onChange={(v) => setRows((a) => a.map((o) => o.id === cur.id ? { ...o, criticality: v as GuidelineDef['criticality'] } : o))} options={[{ value: 'low', label: '低' }, { value: 'medium', label: '中' }, { value: 'high', label: '高' }]} />
              </F>
              <F label="优先级">
                <TextInput mono value={String(cur.priority)} onChange={(v) => setRows((a) => a.map((o) => o.id === cur.id ? { ...o, priority: Number(v) || 0 } : o))} />
              </F>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <span className="text-[12px] font-medium text-[var(--ink-2)]">启用</span>
              <Switch checked={cur.enabled !== false} onChange={(v) => setRows((a) => a.map((o) => o.id === cur.id ? { ...o, enabled: v } : o))} />
            </div>
          </div>
        ) : (
          <div className="px-6 py-20 text-center text-[12.5px] text-[var(--muted)]">选择左侧一条观察进行编辑</div>
        )}
      </div>
    </div>
  )
}
