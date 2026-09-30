/** JSON 导入校验：agent-definition.json → 结构校验（错误带路径定位）+ 引用/重复检查。
 *
 * 设计（plan 阶段4.4）：前端先做即时反馈，后端校验为最终准绳（POST /api/agents 仍兜底）。
 * - error   = 阻止导入（结构残缺/非法，后端保存或引擎加载会失败）
 * - warning = 可导入但需留意（跨引用悬空、重复 id——引擎全局存储会报错/静默覆盖，进构建页后可修）
 */
import type { AgentDefinition } from '../api/agentDefinition'

export interface ImportIssue {
  /** JSON 路径定位，如 journeys.journeys[2].states[1].id */
  path: string
  message: string
  level: 'error' | 'warning'
}

export interface ImportResult {
  ok: boolean
  definition?: AgentDefinition
  /** 导入摘要（agent.id/name，导入确认用） */
  agent?: { id: string; name: string }
  issues: ImportIssue[]
}

// ---------- 类型守卫 / 小工具 ----------
const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)
const isArr = (v: unknown): v is unknown[] => Array.isArray(v)
/** 非空字符串字段 */
const present = (o: Record<string, unknown>, k: string): boolean => {
  const v = o[k]
  return typeof v === 'string' && v.trim() !== ''
}

// ---------- 各「列表型」section 的校验规格（键 → 容器内数组键 + 必填字段） ----------
interface ListSpec {
  itemKey: string
  label: string
  required: [string, string][]
  special?: (item: Record<string, unknown>, path: string, issues: ImportIssue[]) => void
}

const LIST_SPEC: Record<string, ListSpec> = {
  guidelines: {
    itemKey: 'guidelines',
    label: '指南',
    required: [
      ['id', '缺少指南 id'],
      ['condition', '缺少指南条件 condition'],
      ['action', '缺少指南动作 action'],
    ],
  },
  observations: {
    itemKey: 'observations',
    label: '观察',
    required: [
      ['id', '缺少观察 id'],
      ['condition', '缺少观察条件 condition'],
    ],
  },
  variables: {
    itemKey: 'variables',
    label: '变量',
    required: [
      ['id', '缺少变量 id'],
      ['name', '缺少变量名'],
      ['type', '缺少变量类型 type'],
    ],
  },
  glossary: {
    itemKey: 'glossary',
    label: '术语表',
    required: [
      ['id', '缺少术语 id'],
      ['name', '缺少术语名'],
    ],
  },
  canned_responses: {
    itemKey: 'responses',
    label: '预设话术',
    required: [
      ['id', '缺少话术 id'],
      ['template', '缺少话术模板 template'],
    ],
  },
  tools: {
    itemKey: 'tools',
    label: '工具',
    required: [
      ['id', '缺少工具 id'],
      ['name', '缺少工具名'],
    ],
  },
  retrievers: {
    itemKey: 'retrievers',
    label: '检索器',
    required: [
      ['id', '缺少检索器 id'],
      ['title', '缺少检索器标题'],
    ],
  },
  relationships: {
    itemKey: 'relationships',
    label: '关系',
    required: [
      ['id', '缺少关系 id'],
      ['source', '缺少关系源 source'],
      ['target', '缺少关系目标 target'],
      ['kind', '缺少关系类型 kind'],
    ],
    special: (item, path, issues) => {
      // runtime RelationshipDef 为扁平字符串：source/target = 指南id/旅程id/工具名，
      // kind = 关系类型（entailment/priority/dependency/disambiguation/…，见 loader）
      if (present(item, 'kind')) {
        const kinds = ['entailment', 'priority', 'dependency', 'dependency_any', 'disambiguation', 'reevaluation', 'overlap']
        if (!kinds.includes(String(item.kind).toLowerCase())) {
          issues.push({ path: `${path}.kind`, message: `关系类型「${String(item.kind)}」非法（应为 ${kinds.join(' / ')}）`, level: 'warning' })
        }
      }
    },
  },
}

function validateListSection(def: Record<string, unknown>, key: string, spec: ListSpec, issues: ImportIssue[]) {
  const sec = def[key]
  if (sec === undefined) return // 可选 section
  if (!isObj(sec)) {
    issues.push({ path: key, message: `${spec.label}应为对象（{ "${spec.itemKey}": [...] }）`, level: 'error' })
    return
  }
  const list = sec[spec.itemKey]
  if (list === undefined) {
    issues.push({ path: `${key}.${spec.itemKey}`, message: `缺少 ${spec.itemKey} 数组`, level: 'error' })
    return
  }
  if (!isArr(list)) {
    issues.push({ path: `${key}.${spec.itemKey}`, message: `${spec.itemKey} 应为数组`, level: 'error' })
    return
  }
  list.forEach((item, i) => {
    const p = `${key}.${spec.itemKey}[${i}]`
    if (!isObj(item)) {
      issues.push({ path: p, message: '列表项应为对象', level: 'error' })
      return
    }
    for (const [f, m] of spec.required) {
      if (!present(item, f)) issues.push({ path: `${p}.${f}`, message: m, level: 'error' })
    }
    spec.special?.(item, p, issues)
  })
}

// ---------- 旅程（最复杂：节点/转移 + 跨引用/重复 id 检查） ----------
function validateJourneys(def: Record<string, unknown>, issues: ImportIssue[]) {
  const sec = def.journeys
  if (sec === undefined) return
  if (!isObj(sec)) {
    issues.push({ path: 'journeys', message: '旅程应为对象（{ "journeys": [...] }）', level: 'error' })
    return
  }
  const list = sec.journeys
  if (!isArr(list)) {
    issues.push({ path: 'journeys.journeys', message: 'journeys.journeys 应为数组', level: 'error' })
    return
  }
  const seenJ = new Set<string>()
  // stateId -> 所属旅程 id（引擎全局存储：状态 id 跨旅程重复会静默覆盖）
  const allStates = new Map<string, string>()

  list.forEach((j, i) => {
    const p = `journeys.journeys[${i}]`
    if (!isObj(j)) {
      issues.push({ path: p, message: '旅程项应为对象', level: 'error' })
      return
    }
    if (!present(j, 'id')) issues.push({ path: `${p}.id`, message: '缺少旅程 id', level: 'error' })
    else if (seenJ.has(String(j.id))) {
      issues.push({ path: `${p}.id`, message: `旅程 id「${String(j.id)}」重复（引擎全局存储，重复会报错）`, level: 'warning' })
    }
    seenJ.add(String(j.id))
    if (!present(j, 'title')) issues.push({ path: `${p}.title`, message: '缺少旅程标题', level: 'warning' })
    if (!present(j, 'entry_node')) issues.push({ path: `${p}.entry_node`, message: '缺少入口节点 entry_node', level: 'error' })

    const states = j.states
    if (!isArr(states) || states.length === 0) {
      issues.push({ path: `${p}.states`, message: '旅程没有任何状态节点（states 应是非空数组）', level: 'error' })
      return
    }
    const seenS = new Set<string>()
    states.forEach((s, k) => {
      const sp = `${p}.states[${k}]`
      if (!isObj(s)) {
        issues.push({ path: sp, message: '状态节点应为对象', level: 'error' })
        return
      }
      if (!present(s, 'id')) issues.push({ path: `${sp}.id`, message: '缺少状态节点 id', level: 'error' })
      else {
        const sid = String(s.id)
        if (seenS.has(sid)) issues.push({ path: `${sp}.id`, message: `状态 id「${sid}」在旅程内重复`, level: 'warning' })
        seenS.add(sid)
        if (allStates.has(sid)) {
          issues.push({
            path: `${sp}.id`,
            message: `状态 id「${sid}」已被旅程「${allStates.get(sid)}」占用（引擎全局存储，重复会静默覆盖互相污染）`,
            level: 'warning',
          })
        }
        allStates.set(sid, String(j.id ?? `journey[${i}]`))
      }
      if (!present(s, 'title')) issues.push({ path: `${sp}.title`, message: '缺少状态节点标题（界面将回退显示 id）', level: 'warning' })
      const t = s.type
      if (t !== 'chat' && t !== 'tool' && t !== 'fork') {
        issues.push({ path: `${sp}.type`, message: `节点类型「${String(t)}」非法（应为 chat / tool / fork）`, level: 'error' })
      }
    })

    // 跨引用检查（第二遍，需完整 states 列表）
    const sidSet = new Set(states.map((s) => (isObj(s) && present(s, 'id') ? String(s.id) : null)).filter(Boolean) as string[])
    if (present(j, 'entry_node') && !sidSet.has(String(j.entry_node))) {
      issues.push({ path: `${p}.entry_node`, message: `入口节点「${String(j.entry_node)}」在旅程中不存在`, level: 'warning' })
    }
    states.forEach((s, k) => {
      if (!isObj(s)) return
      const sp = `${p}.states[${k}]`
      const transitions = s.transitions
      if (!isArr(transitions)) return
      transitions.forEach((tr, ti) => {
        if (!isObj(tr)) return
        if (present(tr, 'to') && !sidSet.has(String(tr.to))) {
          issues.push({ path: `${sp}.transitions[${ti}].to`, message: `转移指向不存在的状态「${String(tr.to)}」`, level: 'warning' })
        }
      })
    })
  })
}

// 关系 source/target 引用完整性检查：须指向已存在的指南/观察/旅程 id 或内置/remote 工具名。
// 与 runtime loader _resolve_relationship_entity 的解析规则对齐（未命中则运行时跳过该关系）。
function validateRelationships(def: Record<string, unknown>, issues: ImportIssue[]) {
  const sec = def.relationships
  if (!isObj(sec)) return
  const list = sec.relationships
  if (!isArr(list)) return

  const knownIds = new Set<string>()
  for (const key of ['guidelines', 'observations'] as const) {
    const s = def[key]
    if (isObj(s) && isArr(s.guidelines ?? s.observations)) {
      for (const g of (s.guidelines ?? s.observations) as unknown[]) {
        if (isObj(g) && present(g, 'id')) knownIds.add(String(g.id))
      }
    }
  }
  if (isObj(def.journeys) && isArr(def.journeys.journeys)) {
    for (const j of def.journeys.journeys as unknown[]) {
      if (isObj(j) && present(j, 'id')) knownIds.add(String(j.id))
    }
  }
  const toolNames = new Set<string>()
  const toolsSec = def.tools
  if (isObj(toolsSec) && isArr(toolsSec.tools)) {
    for (const t of toolsSec.tools as unknown[]) {
      if (isObj(t) && present(t, 'name')) toolNames.add(String(t.name))
    }
  }

  list.forEach((item, i) => {
    if (!isObj(item)) return
    const p = `relationships.relationships[${i}]`
    for (const side of ['source', 'target'] as const) {
      const ref = item[side]
      if (!present(item, side)) continue
      const s = String(ref)
      const ok = knownIds.has(s) || toolNames.has(s)
      if (!ok) {
        issues.push({ path: `${p}.${side}`, message: `关系 ${side}「${s}」未指向任何指南/观察/旅程/工具（运行时将被跳过）`, level: 'warning' })
      }
    }
  })
}

// ---------- 主入口 ----------
export function parseDefinitionJson(text: string): ImportResult {
  const issues: ImportIssue[] = []
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch (e) {
    return {
      ok: false,
      issues: [{ path: '$', message: `JSON 解析失败：${(e as Error).message}`, level: 'error' }],
    }
  }
  if (!isObj(raw)) {
    return { ok: false, issues: [{ path: '$', message: '顶层必须是 JSON 对象（agent-definition.json）', level: 'error' }] }
  }
  const def = raw as Record<string, unknown>

  // agent（必填）
  const agentRaw = def.agent
  if (!isObj(agentRaw)) {
    issues.push({ path: 'agent', message: '缺少 agent 对象（Agent 元数据）', level: 'error' })
  } else {
    if (!present(agentRaw, 'id')) issues.push({ path: 'agent.id', message: '缺少 agent.id（Agent 唯一标识，server 保存必需）', level: 'error' })
    if (!present(agentRaw, 'name')) issues.push({ path: 'agent.name', message: '缺少 agent.name（界面将回退显示 id）', level: 'warning' })
  }

  // 各列表 section
  for (const [key, spec] of Object.entries(LIST_SPEC)) validateListSection(def, key, spec, issues)
  validateJourneys(def, issues)
  validateRelationships(def, issues)

  const errors = issues.filter((i) => i.level === 'error')
  const agent = isObj(agentRaw)
    ? { id: present(agentRaw, 'id') ? String(agentRaw.id) : '', name: present(agentRaw, 'name') ? String(agentRaw.name) : '' }
    : undefined

  return {
    ok: errors.length === 0,
    definition: errors.length === 0 ? (raw as unknown as AgentDefinition) : undefined,
    agent,
    issues,
  }
}
