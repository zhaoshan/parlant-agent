/** Agent 显示相关的小工具（名称/头像字母 + 空定义模板），供各页面与侧栏共用。 */

import type { AgentDefinition } from '../api/agentDefinition'

/** 新建 Agent 的空定义模板（各组件为空表，进入构建页逐步添加）。草稿版号统一为 draft（发布时 server 覆盖为正式版）。 */
export function newAgentDefinition(id: string, name: string): AgentDefinition {
  return {
    agent: {
      id,
      name,
      version: 'draft',
      default_language: 'zh-CN',
      composition_mode: 'fluid',
      boundary: { allowed: [], prohibited: [] },
      utterances: { greeting: [], preamble: [] },
    },
    guidelines: { guidelines: [] },
    observations: { observations: [] },
    journeys: { journeys: [] },
    variables: { variables: [] },
    glossary: { glossary: [] },
    canned_responses: { responses: [] },
    tools: { tools: [] },
    retrievers: { retrievers: [] },
    relationships: { relationships: [] },
  }
}

/** Agent 显示名：优先 agent.name（去空白），缺失回退 agent_id。 */
export function agentLabel(
  a: { agent_id: string; name?: string | null } | null | undefined,
): string {
  return a?.name?.trim() || a?.agent_id || '未选择'
}

/** 头像字母：取显示名首字符（按名称而非 agent_id code，避免看着像缩写）。 */
export function agentInitial(
  a: { agent_id: string; name?: string | null } | null | undefined,
): string {
  const s = agentLabel(a)
  return s === '未选择' ? '?' : s.slice(0, 1).toUpperCase()
}
