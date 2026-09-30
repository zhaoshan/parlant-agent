/** 简单实体表格模块：变量 / 术语表 / 预设话术 / 工具 / 检索器 —— 表格 + 行内编辑面板。 */
import { useState, type ReactNode } from 'react'
import type { CannedResponseDef, GlossaryTermDef, RetrieverDef, ToolDef, VariableDef } from '../../api/agentDefinition'
import { useBuild } from '../../store/build'
import { ChipsInput, F, Select, Switch, TextInput } from './fields'

type Row = { id: string }
interface Col<T extends Row> {
  key: string
  header: string
  render: (r: T) => ReactNode
}

/** 变量「工具关联」下拉：定义内声明的工具 + 无 + 其它（内置/自定义，转手输）。 */
const CUSTOM_TOOL = '__custom__'

function VariableToolField({ value, onChange, toolNames }: { value: string; onChange: (v: string | undefined) => void; toolNames: string[] }) {
  const [custom, setCustom] = useState(() => Boolean(value && !toolNames.includes(value)))
  const isCustom = custom || (Boolean(value) && !toolNames.includes(value))
  return (
    <div className="flex flex-col gap-1.5">
      <Select
        value={isCustom ? CUSTOM_TOOL : value || ''}
        onChange={(v) => {
          if (v === CUSTOM_TOOL) { setCustom(true); return }
          setCustom(false)
          onChange(v || undefined)
        }}
        options={[
          { value: '', label: '（无，仅默认值）' },
          ...toolNames.map((n) => ({ value: n, label: n })),
          { value: CUSTOM_TOOL, label: '其它（内置/自定义）…' },
        ]}
      />
      {isCustom && (
        <TextInput mono value={value ?? ''} onChange={(x) => onChange(x || undefined)} placeholder="如 tavily_search（内置数据工具）" />
      )}
    </div>
  )
}

function TableView<T extends Row>(props: {
  title: string
  addLabel: string
  cols: Col<T>[]
  rows: T[]
  onAdd: () => void
  onDelete: (id: string) => void
  renderEditor: (r: T) => ReactNode
  selectedId: string | null
  onSelect: (id: string | null) => void
  genId: (prefix: string) => string
  prefix: string
}) {
  const cur = props.rows.find((r) => r.id === props.selectedId) ?? null
  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col border-r border-[var(--line)] bg-[var(--surface)]">
        <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2.5">
          <span className="text-[12.5px] font-semibold">{props.title}</span>
          <span className="mono text-[11px] text-[var(--muted)]">{props.rows.length}</span>
          <button className="ml-auto inline-flex h-7 cursor-pointer items-center rounded-md bg-[var(--primary)] px-2.5 text-[11.5px] font-medium text-white" onClick={props.onAdd}>
            ＋ {props.addLabel}
          </button>
        </div>
        <div className="flex-1 overflow-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-[var(--line)] bg-[#FBFCFD]">
                {props.cols.map((c) => (
                  <th key={c.key} className="whitespace-nowrap px-3.5 py-2 text-[11.5px] font-medium text-[var(--muted)]">{c.header}</th>
                ))}
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {props.rows.map((r) => (
                <tr key={r.id} className={`cursor-pointer border-b border-[var(--line)] hover:bg-[#FAFBFF] ${r.id === props.selectedId ? 'bg-[var(--primary-weak)]' : ''}`} onClick={() => props.onSelect(r.id)}>
                  {props.cols.map((c) => (
                    <td key={c.key} className="px-3.5 py-2.5 text-[12.5px] text-[var(--ink-2)]">{c.render(r)}</td>
                  ))}
                  <td className="px-2 text-right">
                    <button className="cursor-pointer text-[12px] text-[var(--muted)] hover:text-[var(--danger)]" onClick={(e) => { e.stopPropagation(); props.onDelete(r.id) }}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!props.rows.length && <div className="px-6 py-14 text-center text-[12.5px] text-[var(--muted)]">暂无数据</div>}
        </div>
      </div>
      <div className="w-[400px] flex-none overflow-y-auto bg-[var(--surface)]">
        {cur ? (
          <div className="p-5">
            <div className="mb-4 flex items-center gap-2">
              <span className="text-[13px] font-semibold">编辑{props.title}</span>
              <span className="mono text-[10.5px] text-[var(--muted)]">{cur.id}</span>
            </div>
            {props.renderEditor(cur)}
          </div>
        ) : (
          <div className="px-6 py-20 text-center text-[12.5px] text-[var(--muted)]">选择左侧一行进行编辑</div>
        )}
      </div>
    </div>
  )
}

const gid = (p: string) => `${p}_${Math.random().toString(36).slice(2, 8)}`
/** 查重重抽：生成 id 若与现有行冲突则重抽（Math.random 不保证唯一，撞号会导致引擎静默覆盖） */
const uniqueGid = (p: string, existing: Iterable<string>) => {
  const taken = new Set(existing)
  let id = gid(p)
  while (taken.has(id)) id = gid(p)
  return id
}

/* ---------------- 变量 ---------------- */
export function Variables() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const rows = definition?.variables?.variables ?? []
  const setRows = (fn: (arr: VariableDef[]) => VariableDef[]) => update((d) => (d.variables!.variables = fn(d.variables!.variables ?? [])))
  return (
    <TableView<VariableDef>
      title="变量"
      addLabel="新建变量"
      prefix="var"
      genId={gid}
      rows={rows}
      selectedId={selectedId}
      onSelect={setSelected}
      onAdd={() => { const id = uniqueGid('var', rows.map((r) => r.id)); setRows((a) => [...a, { id, name: '', type: 'boolean', description: '' }]); setSelected(id) }}
      onDelete={(id) => setRows((a) => a.filter((v) => v.id !== id))}
      cols={[
        { key: 'name', header: '名称', render: (v) => <span className="mono font-medium text-[var(--ink)]">{v.name || '—'}</span> },
        { key: 'type', header: '类型', render: (v) => <span>{v.type}</span> },
        { key: 'default', header: '默认值', render: (v) => <span className="max-w-[180px] truncate">{String(v.default_value ?? '')}</span> },
        { key: 'tool', header: '工具', render: (v) => (v.tool ? <span className="mono text-[11px] text-[var(--success)]">{v.tool}</span> : <span className="text-[var(--muted)]">—</span>) },
        { key: 'desc', header: '描述', render: (v) => <span className="line-clamp-1 max-w-[220px]">{v.description || ''}</span> },
      ]}
      renderEditor={(v) => {
        const set = (patch: Partial<VariableDef>) => setRows((a) => a.map((x) => (x.id === v.id ? { ...x, ...patch } : x)))
        return (
          <div className="flex flex-col gap-4">
            <F label="名称" hint="旅程/指南引用">
              <TextInput mono value={v.name} onChange={(n) => set({ name: n })} />
            </F>
            <F label="类型">
              <Select value={v.type} onChange={(t) => set({ type: t })} options={[{ value: 'boolean', label: 'boolean 布尔' }, { value: 'string', label: 'string 字符串' }, { value: 'number', label: 'number 数字' }]} />
            </F>
            <F label="默认值" hint="按类型渲染">
              {v.type === 'boolean' ? (
                <Switch checked={Boolean(v.default_value)} onChange={(b) => set({ default_value: b })} />
              ) : (
                <TextInput mono value={String(v.default_value ?? '')} onChange={(x) => set({ default_value: v.type === 'number' ? Number(x) : x })} />
              )}
            </F>
            <F label="允许值 Allowed Values" hint="枚举约束（逗号分隔）">
              <ChipsInput value={Array.isArray(v.allowed_values) ? (v.allowed_values as string[]) : []} onChange={(x) => set({ allowed_values: x })} />
            </F>
            <F label="描述">
              <TextInput rows={2} value={v.description ?? ''} onChange={(x) => set({ description: x })} />
            </F>
            <F label="工具（动态刷新）" hint="为空=静态值；绑定工具后按 freshness 自动调工具刷新变量">
              <VariableToolField
                value={v.tool ?? ''}
                onChange={(x) => set({ tool: x })}
                toolNames={(definition?.tools?.tools ?? []).map((t) => t.name).filter(Boolean)}
              />
            </F>
            <F label="刷新规则 freshness_rules" hint="cron 表达式">
              <TextInput mono value={v.freshness_rules ?? ''} onChange={(x) => set({ freshness_rules: x || null })} />
            </F>
          </div>
        )
      }}
    />
  )
}

/* ---------------- 术语表 ---------------- */
export function Glossary() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const rows = definition?.glossary?.glossary ?? []
  const setRows = (fn: (a: GlossaryTermDef[]) => GlossaryTermDef[]) => update((d) => (d.glossary!.glossary = fn(d.glossary!.glossary ?? [])))
  return (
    <TableView<GlossaryTermDef>
      title="术语表"
      addLabel="新建词条"
      prefix="gls"
      genId={gid}
      rows={rows}
      selectedId={selectedId}
      onSelect={setSelected}
      onAdd={() => { const id = uniqueGid('gls', rows.map((r) => r.id)); setRows((a) => [...a, { id, name: '', description: '' }]); setSelected(id) }}
      onDelete={(id) => setRows((a) => a.filter((x) => x.id !== id))}
      cols={[
        { key: 'name', header: '词条', render: (t) => <span className="font-medium text-[var(--ink)]">{t.name}</span> },
        { key: 'syn', header: '同义词', render: (t) => <span className="text-[var(--muted)]">{(t.synonyms ?? []).join('，')}</span> },
        { key: 'desc', header: '描述', render: (t) => <span className="line-clamp-1 max-w-[260px]">{t.description}</span> },
      ]}
      renderEditor={(t) => {
        const set = (patch: Partial<GlossaryTermDef>) => setRows((a) => a.map((x) => (x.id === t.id ? { ...x, ...patch } : x)))
        return (
          <div className="flex flex-col gap-4">
            <F label="词条名称"><TextInput value={t.name} onChange={(x) => set({ name: x })} /></F>
            <F label="同义词" hint="逗号分隔，帮助命中">
              <ChipsInput value={t.synonyms ?? []} onChange={(x) => set({ synonyms: x })} />
            </F>
            <F label="描述"><TextInput rows={3} value={t.description ?? ''} onChange={(x) => set({ description: x })} /></F>
          </div>
        )
      }}
    />
  )
}

/* ---------------- 预设话术 ---------------- */
export function Canned() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const rows = definition?.canned_responses?.responses ?? []
  const setRows = (fn: (a: CannedResponseDef[]) => CannedResponseDef[]) => update((d) => (d.canned_responses!.responses = fn(d.canned_responses!.responses ?? [])))
  return (
    <TableView<CannedResponseDef>
      title="预设话术"
      addLabel="新建话术"
      prefix="rsp"
      genId={gid}
      rows={rows}
      selectedId={selectedId}
      onSelect={setSelected}
      onAdd={() => { const id = uniqueGid('rsp', rows.map((r) => r.id)); setRows((a) => [...a, { id, template: '' }]); setSelected(id) }}
      onDelete={(id) => setRows((a) => a.filter((x) => x.id !== id))}
      cols={[
        { key: 'template', header: '模板', render: (c) => <span className="block max-w-[320px] truncate whitespace-nowrap">{c.template || '（空模板）'}</span> },
        { key: 'signals', header: '信号', render: (c) => <span className="text-[var(--muted)]">{(c.signals ?? []).length}</span> },
        { key: 'id', header: 'ID', render: (c) => <span className="mono text-[11px] text-[var(--muted)]">{c.id}</span> },
      ]}
      renderEditor={(c) => {
        const set = (patch: Partial<CannedResponseDef>) => setRows((a) => a.map((x) => (x.id === c.id ? { ...x, ...patch } : x)))
        return (
          <div className="flex flex-col gap-4">
            <F label="模板" hint={'支持 {{var}} 插值'}>
              <TextInput rows={4} value={c.template} onChange={(x) => set({ template: x })} />
            </F>
            <F label="标题"><TextInput value={c.title ?? ''} onChange={(x) => set({ title: x })} /></F>
            <F label="触发信号 signals"><ChipsInput value={c.signals ?? []} onChange={(x) => set({ signals: x })} /></F>
            <F label="字段依赖 field_dependencies" hint="需从对话抽取的字段">
              <ChipsInput value={c.field_dependencies ?? []} onChange={(x) => set({ field_dependencies: x })} />
            </F>
            <F label="描述"><TextInput rows={2} value={c.description ?? ''} onChange={(x) => set({ description: x })} /></F>
          </div>
        )
      }}
    />
  )
}

/* ---------------- 工具 ---------------- */
export function Tools() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const rows = definition?.tools?.tools ?? []
  const setRows = (fn: (a: ToolDef[]) => ToolDef[]) => update((d) => (d.tools!.tools = fn(d.tools!.tools ?? [])))
  return (
    <TableView<ToolDef>
      title="工具"
      addLabel="新建工具"
      prefix="tool"
      genId={gid}
      rows={rows}
      selectedId={selectedId}
      onSelect={setSelected}
      onAdd={() => { const id = uniqueGid('tool', rows.map((r) => r.id)); setRows((a) => [...a, { id, name: '', description: '', source: 'remote' }]); setSelected(id) }}
      onDelete={(id) => setRows((a) => a.filter((x) => x.id !== id))}
      cols={[
        { key: 'name', header: '名称', render: (t) => <span className="mono font-medium text-[var(--ink)]">{t.name}</span> },
        { key: 'source', header: '来源', render: (t) => <span>{t.source === 'builtin' ? <span className="text-[var(--success)]">builtin</span> : <span className="text-[var(--primary)]">remote</span>}</span> },
        { key: 'desc', header: '描述', render: (t) => <span className="line-clamp-1 max-w-[240px]">{t.description}</span> },
        { key: 'timeout', header: '超时', render: (t) => <span className="mono text-[11px]">{t.timeout_seconds}s</span> },
      ]}
      renderEditor={(t) => {
        const set = (patch: Partial<ToolDef>) => setRows((a) => a.map((x) => (x.id === t.id ? { ...x, ...patch } : x)))
        return (
          <div className="flex flex-col gap-4">
            <F label="名称（builtin 只读）">
              <TextInput mono value={t.name} readOnly={t.source === 'builtin'} onChange={(x) => set({ name: x })} />
            </F>
            <F label="来源"><Select value={t.source ?? 'remote'} onChange={(x) => set({ source: x as ToolDef['source'] })} options={[{ value: 'remote', label: 'remote 远程服务' }, { value: 'builtin', label: 'builtin 内置' }]} /></F>
            {t.source === 'remote' && (
              <>
                <div className="rounded-lg border border-[var(--primary-line)] bg-[var(--primary-weak)] p-2.5 text-[11px] leading-relaxed text-[var(--primary)]">
                  remote 工具 = 通用 HTTP 调用：声明 <span className="mono">method / url / headers</span>，发起请求并自动注入当前会话的 customer_id。<span className="mono">{'{customer_id}'}</span> 占位可做路径参数。
                </div>
                <F label="请求方法 Method"><Select value={t.method ?? 'GET'} onChange={(x) => set({ method: x })} options={[{ value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' }, { value: 'PUT', label: 'PUT' }, { value: 'DELETE', label: 'DELETE' }]} /></F>
                <F label="URL" hint={'支持 {param} 路径占位，如 http://127.0.0.1:8300/customer/{customer_id}'}>
                  <TextInput mono value={t.url ?? ''} onChange={(x) => set({ url: x })} placeholder="http://127.0.0.1:8300/…" />
                </F>
                <F label="Headers（JSON）" hint={'固定请求头，如 {"Content-Type": "application/json"}'}>
                  <TextInput rows={2} mono value={JSON.stringify(t.headers ?? {}, null, 2)} onChange={(x) => { try { set({ headers: JSON.parse(x) }) } catch { /* 非法 JSON 不落 */ } }} />
                </F>
              </>
            )}
            <F label="描述"><TextInput rows={2} value={t.description ?? ''} onChange={(x) => set({ description: x })} /></F>
            <F label="入参 Schema（JSON）" hint="参数约束">
              <TextInput rows={6} mono value={JSON.stringify(t.input_schema ?? {}, null, 2)} onChange={(x) => { try { set({ input_schema: JSON.parse(x) }) } catch { /* 非法 JSON 不落 */ } }} />
            </F>
            <F label="超时（秒）"><TextInput mono value={String(t.timeout_seconds ?? '')} onChange={(x) => set({ timeout_seconds: Number(x) || 0 })} /></F>
            <F label="重要结果 Consequential" hint="命中后重新评估指南">
              <div className="flex items-center gap-2"><Switch checked={t.consequential ?? false} onChange={(x) => set({ consequential: x })} /><span className="text-[12px] text-[var(--ink-2)]">{t.consequential ? '是' : '否'}</span></div>
            </F>
          </div>
        )
      }}
    />
  )
}

/* ---------------- 检索器 ---------------- */
export function Retrievers() {
  const { definition, update, selectedId, setSelected } = useBuild()
  const rows = definition?.retrievers?.retrievers ?? []
  const setRows = (fn: (a: RetrieverDef[]) => RetrieverDef[]) => update((d) => (d.retrievers!.retrievers = fn(d.retrievers!.retrievers ?? [])))
  return (
    <TableView<RetrieverDef>
      title="检索器"
      addLabel="新建检索器"
      prefix="rtr"
      genId={gid}
      rows={rows}
      selectedId={selectedId}
      onSelect={setSelected}
      onAdd={() => { const id = uniqueGid('rtr', rows.map((r) => r.id)); setRows((a) => [...a, { id, title: '', description: '', type: 'ragflow_http' }]); setSelected(id) }}
      onDelete={(id) => setRows((a) => a.filter((x) => x.id !== id))}
      cols={[
        { key: 'title', header: '名称', render: (r) => <span className="font-medium text-[var(--ink)]">{r.title}</span> },
        { key: 'type', header: '类型', render: (r) => <span className="mono text-[11px]">{r.type}</span> },
        { key: 'endpoint', header: 'Endpoint', render: (r) => <span className="line-clamp-1 max-w-[200px] text-[var(--muted)]">{r.endpoint || '—'}</span> },
        { key: 'topk', header: 'Top-K', render: (r) => <span className="mono text-[11px]">{r.top_k ?? '—'}</span> },
      ]}
      renderEditor={(r) => {
        const set = (patch: Partial<RetrieverDef>) => setRows((a) => a.map((x) => (x.id === r.id ? { ...x, ...patch } : x)))
        return (
          <div className="flex flex-col gap-4">
            <F label="名称"><TextInput value={r.title} onChange={(x) => set({ title: x })} /></F>
            <F label="类型"><TextInput mono value={r.type ?? ''} onChange={(x) => set({ type: x })} /></F>
            <F label="描述"><TextInput rows={2} value={r.description ?? ''} onChange={(x) => set({ description: x })} /></F>
            <F label="连接配置">
              <div className="flex flex-col gap-2">
                <TextInput value={r.endpoint ?? ''} onChange={(x) => set({ endpoint: x })} placeholder="Endpoint" />
                <TextInput value={r.collection ?? ''} onChange={(x) => set({ collection: x })} placeholder="Collection" />
              </div>
            </F>
            <F label="检索参数">
              <div className="grid grid-cols-2 gap-2">
                <TextInput mono value={String(r.top_k ?? '')} onChange={(x) => set({ top_k: Number(x) || 0 })} placeholder="top_k" />
                <TextInput mono value={String(r.min_score ?? '')} onChange={(x) => set({ min_score: x ? Number(x) : null })} placeholder="min_score" />
                <TextInput mono value={String(r.fetch_limit ?? '')} onChange={(x) => set({ fetch_limit: Number(x) || 0 })} placeholder="fetch_limit" />
                <TextInput mono value={String(r.timeout_seconds ?? '')} onChange={(x) => set({ timeout_seconds: Number(x) || 0 })} placeholder="timeout(s)" />
              </div>
            </F>
            <F label="状态">
              <Select value={r.status ?? 'active'} onChange={(x) => set({ status: x })} options={[{ value: 'active', label: 'active' }, { value: 'inactive', label: 'inactive' }]} />
            </F>
          </div>
        )
      }}
    />
  )
}
