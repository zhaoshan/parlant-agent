/** Agent 显示相关的小工具（名称/头像字母），供各页面与侧栏共用。 */

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
