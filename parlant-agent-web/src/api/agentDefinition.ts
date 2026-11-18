/** Agent 定义结构（对应 agent-definition.json）——构建页草稿编辑的领域模型。 */

export interface AgentDefMeta {
  id: string
  name: string
  version: string
  description?: string
  default_language?: string
  tags?: string[]
  metadata?: Record<string, unknown>
  composition_mode?: string
  boundary?: { allowed: string[]; prohibited: string[]; emergency_action?: string }
  utterances?: {
    greeting?: string[]
    preamble?: string[]
    system_error_fallback?: string
    timeout_fallback?: string
  }
}

export interface GuidelineDef {
  id: string
  condition: string
  action: string
  criticality: 'low' | 'medium' | 'high'
  priority: number
  enabled: boolean
  category?: string
  scope?: string
  composition_mode?: string
  description?: string
  title?: string
  canned_responses?: string[]
  journey_ids?: string[]
  node_ids?: string[]
  tools?: string[]
  retrievers?: string[]
  labels?: string[]
  tags?: string[]
  dependencies?: string[]
  track?: boolean
  variable_conditions?: unknown[]
  variable_updates_on_match?: unknown[]
  trigger_observations?: unknown[]
}

export interface JourneyTransitionDef {
  transition_id?: string
  condition?: string
  to?: string
  keywords?: string[]
  patterns?: string[]
  intent?: string
  intent_labels?: string[]
  topic_terms?: string[]
  exclude_keywords?: string[]
  response_mode?: string
  timeout_branch?: boolean
  resume_state_id?: string | null
  variable_conditions?: unknown[]
  canned_responses?: string[]
}

export interface JourneyStateDef {
  id: string
  title: string
  description?: string
  type: 'chat' | 'tool' | 'fork'
  chat_state?: string
  tool_instruction?: string
  priority?: number
  composition_mode?: string
  labels?: string[]
  metadata?: Record<string, unknown>
  transitions?: JourneyTransitionDef[]
  variable_updates_on_enter?: unknown[]
  variable_updates_on_exit?: unknown[]
  variable_conditions?: unknown[]
  tools?: string[]
  variables?: string[]
  tool_state?: string[]
  canned_responses?: string[]
  retrievers?: string[]
}

export interface JourneyDef {
  id: string
  title: string
  description?: string
  business_goal?: string
  sop_type?: string
  priority?: number
  entry_node?: string
  composition_mode?: string
  status?: string
  triggers?: string[]
  states?: JourneyStateDef[]
  dependencies?: string[]
  retrievers?: string[]
  labels?: string[]
  tags?: string[]
}

export interface VariableDef {
  id: string
  name: string
  description?: string
  type: 'boolean' | 'string' | 'number' | string
  default_value?: unknown
  allowed_values?: unknown[]
  freshness_rules?: string | null
  tool?: string
  bound_to?: string
  tags?: string[]
  metadata?: Record<string, unknown>
}

export interface GlossaryTermDef {
  id: string
  name: string
  description?: string
  synonyms?: string[]
  bound_to?: string
  tags?: string[]
}

export interface CannedResponseDef {
  id: string
  title?: string
  template: string
  description?: string
  signals?: string[]
  field_dependencies?: string[]
  bound_to?: string
  tags?: string[]
  usage_context?: string
}

export interface ToolDef {
  id: string
  name: string
  description?: string
  source?: 'builtin' | 'remote' | string
  type?: string
  server_id?: string | null
  remote_name?: string | null
  input_schema?: Record<string, unknown>
  input_fields?: { name: string; type?: string; required?: boolean; desc?: string }[]
  output_fields?: unknown[]
  config?: unknown
  retry?: number
  timeout_seconds?: number
  consequential?: boolean
  /** remote 远程服务专用：通用 HTTP 工具配置（method/url/headers），实现见
   *  parlant-agent-runtime/app/services/http_tools.py */
  method?: string
  url?: string
  headers?: Record<string, string>
  /** remote 专用：工具结果 → 变量自动回写（仅成功响应），{变量名: 结果取值路径}，
   *  路径基于 {"status","data"} 点号寻址（如 data.orderStatus / data.items.0.code） */
  variable_mappings?: Record<string, string>
  editable?: boolean
}

export interface RetrieverDef {
  id: string
  title: string
  description?: string
  type?: string
  endpoint?: string
  collection?: string
  db_path?: string
  document_ids?: string[]
  knowledge_scope?: string
  top_k?: number
  fetch_limit?: number
  min_score?: number | null
  context_min_score_default?: number
  min_query_length?: number
  timeout_seconds?: number
  term_rewrite_enabled?: boolean
  status?: string
  global?: boolean
  metadata_filter?: Record<string, unknown>
  customer_metadata_filter_map?: Record<string, unknown>
}

export interface RelationshipDef {
  id: string
  /** 源实体引用：指南/观察 id（gdl_* 或 obs_*）、旅程 id（jny_*）或工具名；运行时按 id 解析实体 */
  source: string
  /** 关系类型：entailment / priority / dependency / dependency_any / disambiguation / reevaluation / overlap */
  kind: string
  /** 目标实体引用（同 source） */
  target: string
  description?: string
}

export interface AgentDefinition {
  agent: AgentDefMeta
  guidelines?: { guidelines: GuidelineDef[] }
  journeys?: { journeys: JourneyDef[] }
  variables?: { variables: VariableDef[] }
  glossary?: { glossary: GlossaryTermDef[] }
  canned_responses?: { responses: CannedResponseDef[] }
  tools?: { tools: ToolDef[] }
  retrievers?: { retrievers: RetrieverDef[] }
  relationships?: { relationships: RelationshipDef[] }
  observations?: { observations: GuidelineDef[] }
}
