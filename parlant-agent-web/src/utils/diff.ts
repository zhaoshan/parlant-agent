/** agent-definition.json 结构化差异：按板块列 新增/删除/修改，修改项给出**字段级**变化（路径 + 旧值→新值），用于发布前对比与版本历史对比。 */

export interface FieldChange {
  /** 变化路径：agent.version、guidelines[xxx].condition、journeys[jny].states[sta].chat_state… */
  path: string
  kind: 'modified' | 'added' | 'removed'
  old?: unknown
  new?: unknown
}

export interface ItemChange {
  /** 条目标签（指南条件 / 旅程标题 / 状态标题…） */
  label: string
  /** 该条目内的字段级变化（空 = 仅结构变化，展示整条 JSON） */
  changes: FieldChange[]
}

export interface SectionDiff {
  key: string
  label: string
  added: string[]
  removed: string[]
  modified: ItemChange[]
}

export interface DefinitionDiff {
  sections: SectionDiff[]
  /** 是否有任何变更（无 = 两版本完全一致） */
  same: boolean
  total: number
}

/** 板块定义：key 对应 definition 顶层字段，label 为展示名，list 取列表字段（agent 特殊：对象字段对比）。 */
const SECTIONS: { key: string; label: string; list: string; id?: string; desc: string }[] = [
  { key: 'agent', label: '基础信息', list: '', id: '', desc: '字段' },
  { key: 'guidelines', label: '指南 Guidelines', list: 'guidelines', id: 'id', desc: '指南' },
  { key: 'journeys', label: '旅程 Journeys', list: 'journeys', id: 'id', desc: '旅程' },
  { key: 'variables', label: '变量 Variables', list: 'variables', id: 'name', desc: '变量' },
  { key: 'glossary', label: '术语表 Glossary', list: 'glossary', id: 'id', desc: '术语' },
  { key: 'canned_responses', label: '预设话术 Canned Responses', list: 'responses', id: 'id', desc: '话术' },
  { key: 'tools', label: '工具 Tools', list: 'tools', id: 'id', desc: '工具' },
  { key: 'retrievers', label: '检索器 Retrievers', list: 'retrievers', id: 'id', desc: '检索器' },
  { key: 'relationships', label: '关系 Relationships', list: 'relationships', id: 'id', desc: '关系' },
  { key: 'observations', label: '观察 Observations', list: 'observations', id: 'id', desc: '观察' },
]

const EMPTY: Record<string, unknown> = {}

function jsonOf(v: unknown): string {
  try {
    return JSON.stringify(v ?? null)
  } catch {
    return String(v)
  }
}

/** 人读的条目标签：取最像名称/内容的字段。 */
function describe(item: unknown): string {
  const o = item as Record<string, unknown> | null
  if (!o || typeof o !== 'object') return String(item ?? '')
  for (const k of ['title', 'name', 'template', 'condition', 'description', 'action', 'id']) {
    const v = o[k]
    if (typeof v === 'string' && v) return v.length > 40 ? `${v.slice(0, 40)}…` : v
  }
  return String(o.id ?? '')
}

/** 数组元素匹配：有稳定 id 按 id 匹配（states 按 id、transitions 按 transition_id）。 */
function arrayKey(x: unknown): string | null {
  if (!x || typeof x !== 'object') return null
  const o = x as Record<string, unknown>
  for (const k of ['id', 'transition_id', 'name']) {
    const v = o[k]
    if (typeof v === 'string' && v) return `${k}=${v}`
  }
  return null
}

/** 路径展示用短标签：`id=sta_x` → `sta_x`；`transition_id=txn_x` → 转移条件文案。 */
function shortPath(k: string): string {
  const i = k.indexOf('=')
  const key = i >= 0 ? k.slice(0, i) : ''
  const val = i >= 0 ? k.slice(i + 1) : k
  if (key === 'transition_id') return val.length > 22 ? `${val.slice(0, 22)}…` : val
  return val
}

/**
 * 递归收集两个值之间的字段级差异（扁平输出，路径可读）。
 * - 对象：按 key 递归；数组：按稳定 id 配对递归，无法配对记为 新增/删除 整项。
 */
function collect(path: string, oldV: unknown, newV: unknown, out: FieldChange[]): void {
  const bothObj = oldV && newV && typeof oldV === 'object' && typeof newV === 'object' && !Array.isArray(oldV) && !Array.isArray(newV)
  const bothArr = Array.isArray(oldV) && Array.isArray(newV)

  if (bothObj) {
    const o = oldV as Record<string, unknown>
    const n = newV as Record<string, unknown>
    for (const k of Object.keys(n)) {
      if (!(k in o)) out.push({ path: `${path}.${k}`, kind: 'added', new: n[k] })
      else if (jsonOf(o[k]) !== jsonOf(n[k])) collect(`${path}.${k}`, o[k], n[k], out)
    }
    for (const k of Object.keys(o)) if (!(k in n)) out.push({ path: `${path}.${k}`, kind: 'removed', old: o[k] })
    return
  }

  if (bothArr) {
    const o = oldV as unknown[]
    const n = newV as unknown[]
    const om = new Map<string, unknown>()
    o.forEach((x, i) => { const k = arrayKey(x); om.set(k ?? `#${i}`, x) })
    const nm = new Map<string, unknown>()
    n.forEach((x, i) => { const k = arrayKey(x); nm.set(k ?? `#${i}`, x) })
    for (const [k, x] of nm) {
      if (!om.has(k)) out.push({ path: `${path}[${shortPath(k)}]`, kind: 'added', new: x })
      else if (jsonOf(x) !== jsonOf(om.get(k))) collect(`${path}[${shortPath(k)}]`, om.get(k), x, out)
    }
    for (const [k, x] of om) if (!nm.has(k)) out.push({ path: `${path}[${shortPath(k)}]`, kind: 'removed', old: x })
    return
  }

  // 标量不同：记录旧值→新值
  out.push({ path, kind: 'modified', old: oldV, new: newV })
}

/** 单个条目的字段级变化（dict 且非数组）；扁平数组/标量对象直接给整条差异。 */
function itemChanges(item: unknown, oldItem: unknown): FieldChange[] {
  const bothObj = item && oldItem && typeof item === 'object' && typeof oldItem === 'object' && !Array.isArray(item) && !Array.isArray(oldItem)
  const out: FieldChange[] = []
  if (bothObj) collect('', oldItem, item, out)
  else out.push({ path: '', kind: 'modified', old: oldItem, new: item })
  return out
}

/** 对比两份 agent-definition.json，产出板块级差异（修改项带字段级详情）。 */
export function diffDefinitions(a: unknown, b: unknown): DefinitionDiff {
  const oldRoot = (a ?? {}) as Record<string, unknown>
  const newRoot = (b ?? {}) as Record<string, unknown>
  const sections: SectionDiff[] = []
  let total = 0

  for (const sec of SECTIONS) {
    const added: string[] = []
    const removed: string[] = []
    const modified: ItemChange[] = []

    if (!sec.list) {
      // agent 对象：每个变化字段为一个 ItemChange
      const oldObj = (oldRoot[sec.key] ?? EMPTY) as Record<string, unknown>
      const newObj = (newRoot[sec.key] ?? EMPTY) as Record<string, unknown>
      for (const k of Object.keys(newObj)) {
        if (!(k in oldObj)) added.push(k)
        else if (jsonOf(newObj[k]) !== jsonOf(oldObj[k])) modified.push({ label: k, changes: [{ path: k, kind: 'modified', old: oldObj[k], new: newObj[k] }] })
      }
      for (const k of Object.keys(oldObj)) if (!(k in newObj)) removed.push(k)
      if (added.length || removed.length || modified.length) {
        sections.push({ key: sec.key, label: sec.label, added, removed, modified })
        total += added.length + removed.length + modified.length
      }
      continue
    }

    const oldList = (((oldRoot[sec.key] ?? EMPTY) as Record<string, unknown>)[sec.list] ?? []) as unknown[]
    const newList = (((newRoot[sec.key] ?? EMPTY) as Record<string, unknown>)[sec.list] ?? []) as unknown[]
    const oldMap = new Map(oldList.map((x) => [(x as Record<string, unknown>)[sec.id!], x]))
    const newMap = new Map(newList.map((x) => [(x as Record<string, unknown>)[sec.id!], x]))
    for (const [id, item] of newMap) {
      if (!oldMap.has(id)) added.push(describe(item))
      else if (jsonOf(item) !== jsonOf(oldMap.get(id))) modified.push({ label: describe(item), changes: itemChanges(item, oldMap.get(id)) })
    }
    for (const [id, item] of oldMap) if (!newMap.has(id)) removed.push(describe(item))
    if (added.length || removed.length || modified.length) {
      sections.push({ key: sec.key, label: sec.label, added, removed, modified })
      total += added.length + removed.length + modified.length
    }
  }

  return { sections, same: total === 0, total }
}
