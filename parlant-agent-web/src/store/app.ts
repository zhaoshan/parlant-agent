/** 全局状态：当前 Agent 上下文 + 当前用户（AgentStudio 单 Agent 工作台）。 */
import { create } from 'zustand'
import type { AgentInfo } from '../api/types'

export interface CurrentUser {
  user_id: string
  user_name: string
}

interface AppState {
  agents: AgentInfo[]
  currentAgent: AgentInfo | null
  currentUser: CurrentUser
  setAgents: (agents: AgentInfo[]) => void
  setCurrentAgent: (agent: AgentInfo | null) => void
}

export const useApp = create<AppState>((set) => ({
  agents: [],
  // MVP 演示用户；后续接入登录后替换
  currentAgent: null,
  currentUser: { user_id: 'u-demo', user_name: '演示用户' },
  setAgents: (agents) => set({ agents }),
  setCurrentAgent: (currentAgent) => set({ currentAgent }),
}))
