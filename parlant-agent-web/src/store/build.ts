/** Agent 构建页草稿状态：加载定义 → 本地编辑（草稿）→ 保存/发布。 */
import { create } from 'zustand'
import type { AgentDefinition } from '../api/agentDefinition'

export type BuildModule =
  | 'basics'
  | 'boundaries'
  | 'guidelines'
  | 'journeys'
  | 'variables'
  | 'glossary'
  | 'canned'
  | 'tools'
  | 'retrievers'
  | 'relationships'
  | 'observations'

interface BuildState {
  agentId: string | null
  /** 已加载的定义（草稿工作副本） */
  definition: AgentDefinition | null
  /** 加载时的原始定义（diff 用） */
  original: AgentDefinition | null
  loading: boolean
  module: BuildModule
  /** 当前选中的子项 id（列表行） */
  selectedId: string | null
  load: (agentId: string, definition: AgentDefinition) => void
  setModule: (m: BuildModule) => void
  setSelected: (id: string | null) => void
  update: (fn: (d: AgentDefinition) => void) => void
  markSaved: () => void
}

export const useBuild = create<BuildState>((set, get) => ({
  agentId: null,
  definition: null,
  original: null,
  loading: false,
  module: 'basics',
  selectedId: null,
  load: (agentId, definition) =>
    set({ agentId, definition: structuredClone(definition), original: structuredClone(definition), selectedId: null }),
  setModule: (module) => set({ module, selectedId: null }),
  setSelected: (selectedId) => set({ selectedId }),
  update: (fn) => {
    const d = get().definition
    if (!d) return
    fn(d)
    set({ definition: { ...d } })
  },
  markSaved: () => set({ original: structuredClone(get().definition) }),
}))
