# 阶段7：技能平台（Skills）——创建/诊断 Agent 的平台级能力

> 2026-09-30 新增。定位：把「手工搭 Agent + 排障」沉淀为可复用、可调度、可配置模型的
> **平台级技能**。源于智能投顾 Demo 的实战积累（journey priority 须≥最高指南、
> strict 兜底坑、跨 Agent id 全局唯一、relationship 悬空引用、变量 freshness、
> 分叉条件表就绪等，见 docs/03-production/11 与各排障文档）。
> 概念澄清：v3.3.1 无原生 skill 概念（schema `skills` 键为空壳、源码未消费），
> 本阶段是**全新平台概念**；与 Claude Code skills（.claude/skills）互不相关。

## 1. 核心机制

**技能 = 一个可配置实体 + 一个独立模型驱动的执行器（skill-runner）**，与客服 runtime 完全解耦：

```
技能配置（prompt + model + 输入/输出 schema + 工作流）→ Mongo（定义层同款草稿/发布管理）
  → 触发执行（Web 首页「新建 Agent 选技能」 / 技能管理页 / 客服 Agent 对话中经 remote 工具调度）
  → skill-runner（独立服务/进程）：
       • 按 skill.model 调 LLM（独立于引擎执行模型 deepseek-v4.1-flash）
       • 注入上下文：定义快照 / 会话记录（MySQL session_messages）/ langfuse 追踪 / 约束知识库
       • 执行多步 agentic 工作流（生成→校验→改→再校验；读会话→比对→结论）
  → 结果回 Web（诊断报告 / 草稿定义 / 回复判定）
```

**关键设计**：
- **模型隔离**：每个技能 `model` 独立配置，管理任务不占用/不被客服引擎模型拖累
- **解耦**：skill-runner 独立进程（独立配额/超时/限流/故障），与客服 runtime 互不影响
- **确定性校验优先**：配置诊断的多数规则是确定性实现的（非 LLM 发挥），LLM 只做补充解释
- **写操作护栏**：技能创建 Agent 只落到**草稿**，产出强校验 + 发布前人工确认
- **可调度**：`POST /skills/{id}/run` 可包成 remote HTTP 工具（复用 http_tools.py 通用内核），客服 Agent 对话中即可调用诊断技能

## 2. 交付物

### 后端（parlant-agent-server 扩展）
- **技能配置实体 + CRUD**：schema = `id/name/description/model/input_schema/prompt/工作流/output_schema`；Mongo 存储，草稿/发布管理（沿用定义层模式）
- **skill-runner 服务**（可独立进程）：按技能模型调 LLM（复用 LiteLLM 基建）；多步工具调用循环（读定义/读会话/写草稿）；上下文注入（定义快照、session_messages、langfuse 追踪、约束知识库）
- **确定性校验器库**：复用并扩展现有校验（server 跨 Agent id 预检、导入校验 definitionImport、loader 装配告警），新增旅程配置约束（priority 阈值、strict 兜底、分叉条件表就绪）
- **`POST /skills/{id}/run`**：技能执行入口（同步结果或异步任务+轮询）
- **remote 工具包装**：`skills/{id}/run` 注册为 remote 工具，供客服 Agent 对话中调度

### 前端（parlant-agent-web）
- **Agent 首页「新建 Agent」**：增加「用技能创建/诊断」选项（技能选择 → 输入需求/配置 → 展示诊断报告或生成草稿）
- **技能管理页**：技能列表 + 新建/编辑（prompt/模型/输入 schema）+ 手动添加技能
- **诊断结果展示**：问题清单（级别/定位/修复建议）、回复判定结论（期望 vs 实际）

### 预置技能（3 个默认）
1. **Agent 配置诊断**（`agent-config-diagnose`）：定义 → 引擎约束校验 → 结构化问题清单。确定性为主，价值最高，**Phase 1 先做**
2. **回复是否符合预期**（`reply-diagnose`）：定义快照 + 会话记录 + langfuse 追踪 → 判定该轮回复是否遵循指南/旅程预期。**Phase 2**
3. **Agent 创建**（`agent-create`）：需求描述 → 生成定义骨架 → 自动跑①校验 → 修 → 存草稿。半自动辅助（业务语义需人确认）。**Phase 3**

## 3. 验收标准

- [ ] 技能 CRUD + 草稿/发布闭环；用户可手动添加技能（自定义 prompt/模型/输入 schema）
- [ ] skill-runner 按技能 model 独立调 LLM，与客服引擎模型互不影响
- [ ] **配置诊断技能**：对已知缺陷定义（priority 过低 / strict 指南 / id 冲突 / 悬空关系）能逐项报出并给修复建议；对通过定义零误报
- [ ] **回复诊断技能**：基于某会话记录 + trace 判定"是否遵循指南/旅程预期"，结论有依据（引用命中的指南/旅程状态）
- [ ] **创建技能**：能生成通过配置诊断的定义草稿（不要求一次业务正确，要求合法 + 可进诊断迭代）
- [ ] Web：Agent 首页新建 Agent 可选技能；诊断结果可视化；技能管理页可用
- [ ] remote 工具调度：客服 Agent 对话中能调用 `skills/.../run` 执行诊断并返回结果
- [ ] 写操作（创建→草稿）不直接 publish，有人工确认

## 4. 依赖

- 阶段3 server（技能 API/管理）、阶段4 web 配置管理（技能管理页复用）、阶段5 生产化基建
- 可观测性（langfuse 追踪、MySQL session_messages）——回复诊断技能的数据源
- 确定性校验：阶段4 导入校验（definitionImport）、阶段7 服务器跨 Agent id 预检、loader 装配告警
- remote HTTP 工具内核（http_tools.py）——工具调度技能的底座

## 5. 实施顺序

- **7.1 技能框架**：配置 schema + CRUD + skill-runner 骨架 + Web 触发入口 + 技能管理页
- **7.2 配置诊断技能**：确定性校验器库 + 预置技能① + 诊断结果展示
- **7.3 回复诊断技能**：接会话记录/trace + 预置技能②
- **7.4 创建技能**：生成→校验→迭代→存草稿 + 预置技能③
- **7.5 工具调度 + 自定义开放**：skills/{id}/run 包 remote 工具；用户自定义技能管理完整化
