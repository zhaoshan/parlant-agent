/** 从 JSON 导入 Agent：粘贴/上传 agent-definition.json → 结构校验（错误定位）→ 存草稿并进入构建页。
 *
 * 流程（plan 阶段4.4）：
 * 1. 粘贴 JSON 文本 或 选择 .json 文件；
 * 2. 点「导入」→ parseDefinitionJson 校验：error 阻塞并列出定位；warning 允许导入（可进构建页再修）；
 * 3. 校验通过 → POST /api/agents 存为草稿（已有同名草稿会被覆盖）→ 回调 onCreated(agent_id)。
 */
import { useRef, useState } from 'react'
import { agentsApi } from '../api/client'
import { parseDefinitionJson, type ImportIssue } from '../utils/definitionImport'

interface Props {
  onClose: () => void
  /** 导入成功（已存草稿），回调 agent_id（父组件刷新列表并进入构建页） */
  onCreated: (agentId: string) => void
}

export default function ImportDialog({ onClose, onCreated }: Props) {
  const [text, setText] = useState('')
  const [fileName, setFileName] = useState('')
  const [issues, setIssues] = useState<ImportIssue[] | null>(null)
  const [summary, setSummary] = useState<{ id: string; name: string; counts: Record<string, number> } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const loadFile = (f: File | undefined) => {
    if (!f) return
    setFileName(f.name)
    setErr('')
    const reader = new FileReader()
    reader.onload = () => {
      const s = typeof reader.result === 'string' ? reader.result : ''
      setText(s)
      setIssues(null)
      setSummary(null)
    }
    reader.readAsText(f)
  }

  const errors = issues?.filter((i) => i.level === 'error') ?? []
  const warnings = issues?.filter((i) => i.level === 'warning') ?? []
  // 点击即「校验 + 导入」单步：doImport 内重新 parseDefinitionJson，error 阻断并列出定位、
  // warning 放行；故这里只需文本非空且无 error（issues 为 null 时尚未校验，errors=[] 不阻塞）。
  // ⚠️ 不能要求 issues !== null——issues 只在 doImport（按钮点击）里赋值，那样按钮永远置灰。
  const canImport = !!text.trim() && errors.length === 0 && !busy

  const doImport = async () => {
    const r = parseDefinitionJson(text)
    setIssues(r.issues)
    if (!r.ok || !r.definition) return
    // 导入 = 保存为草稿：归一化 agent.version 为 draft，避免构建页徽标误显示成已发布版本号
    // （发布时 server 会以目标正式版本号覆盖）
    const def = structuredClone(r.definition)
    def.agent = { ...def.agent, version: 'draft' }
    // 组件统计摘要（导入确认用）
    const d = def as unknown as Record<string, { [k: string]: unknown[] } | undefined>
    const sec = (k: string, arr: string) => d[k]?.[arr]?.length ?? 0
    setSummary({
      id: r.agent?.id ?? '',
      name: r.agent?.name ?? '',
      counts: {
        指南: sec('guidelines', 'guidelines'),
        旅程: sec('journeys', 'journeys'),
        变量: sec('variables', 'variables'),
        术语: sec('glossary', 'glossary'),
        话术: sec('canned_responses', 'responses'),
        工具: sec('tools', 'tools'),
        检索器: sec('retrievers', 'retrievers'),
        关系: sec('relationships', 'relationships'),
      },
    })
    setBusy(true)
    setErr('')
    try {
      const created = await agentsApi.create(def)
      onCreated(created.agent_id)
    } catch (e) {
      setErr(String(e))
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-60 grid place-items-center bg-[rgba(15,23,42,.45)]" onClick={onClose}>
      <div className="w-[640px] max-h-[88vh] overflow-auto rounded-xl bg-[var(--surface)] p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-[15px] font-semibold">从 JSON 导入 Agent</h3>
            <p className="mt-1 text-[12px] text-[var(--muted)]">
              粘贴 agent-definition.json 或选择文件；校验通过后保存为草稿并进入构建页编辑
              <span className="mono ml-1">（POST /api/agents）</span>
            </p>
          </div>
          <button className="cursor-pointer rounded-md p-1 text-[var(--muted)] hover:bg-[#EDF0F4]" onClick={onClose}>✕</button>
        </div>

        {/* 输入区：textarea + 选文件 */}
        <div className="mt-3">
          <textarea
            className="mono h-[240px] w-full resize-y rounded-lg border border-[var(--line-strong)] bg-[var(--bg)] p-3 text-[11.5px] leading-relaxed text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)]"
            placeholder='粘贴 JSON…（例如 {"agent": {"id": "onb-xxx", "name": "…", ...}}）'
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setIssues(null)
              setSummary(null)
            }}
            spellCheck={false}
          />
          <div className="mt-2 flex items-center gap-2 text-[11.5px] text-[var(--muted)]">
            <input
              ref={fileRef}
              type="file"
              accept=".json,application/json"
              className="hidden"
              onChange={(e) => loadFile(e.target.files?.[0])}
            />
            <button
              className="inline-flex h-7 items-center rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-2.5 text-[11.5px] text-[var(--ink-2)] hover:bg-[#F1F5F9]"
              onClick={() => fileRef.current?.click()}
            >
              选择文件…
            </button>
            {fileName && <span className="mono truncate text-[10.5px]">{fileName}</span>}
            {text && !issues && <span className="ml-auto text-[11px]">点「导入」进行校验</span>}
          </div>
        </div>

        {/* 校验结果 */}
        {err && (
          <div className="mt-3 rounded-lg border border-[#FECACA] bg-[#FEF2F2] p-2.5 text-[11.5px] text-[var(--danger)]">{err}</div>
        )}
        {issues !== null && (
          <div className="mt-3">
            {errors.length === 0 && warnings.length === 0 && summary && (
              <div className="rounded-lg border border-[#D1FAE5] bg-[#ECFDF5] p-3">
                <div className="flex items-center gap-2 text-[12px] font-semibold text-[#059669]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#059669]" /> 校验通过 · 可导入
                  <span className="mono ml-auto text-[11px] font-normal text-[#6EE7B7]">✓ {summary.id}</span>
                </div>
                <div className="mt-1 text-[11px] text-[#047857]">{summary.name} · 将保存为草稿并进入构建页编辑</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(summary.counts).map(([k, n]) => (
                    <span key={k} className="rounded bg-white/70 px-1.5 py-0.5 text-[10.5px] text-[#047857]">
                      {k} <b className="mono">{n}</b>
                    </span>
                  ))}
                </div>
              </div>
            )}
            {errors.length > 0 && (
              <div className="rounded-lg border border-[#FECACA] bg-[#FEF2F2] p-2.5">
                <div className="mb-1.5 text-[11.5px] font-semibold text-[var(--danger)]">校验未通过 · {errors.length} 处错误（修复后才能导入）</div>
                <div className="max-h-[150px] overflow-auto">
                  {errors.map((i, idx) => (
                    <div key={idx} className="flex items-start gap-1.5 py-0.5 text-[11.5px] leading-relaxed text-[var(--danger)]">
                      <span className="mono mt-px flex-none rounded bg-white/70 px-1 text-[10px]">{i.path}</span>
                      <span>{i.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {warnings.length > 0 && (
              <div className="mt-2 rounded-lg border border-[#FDE68A] bg-[var(--warning-weak)] p-2.5">
                <div className="mb-1.5 text-[11.5px] font-semibold text-[var(--warning)]">{warnings.length} 处提示（不阻塞导入，可进构建页修复）</div>
                <div className="max-h-[120px] overflow-auto">
                  {warnings.map((i, idx) => (
                    <div key={idx} className="flex items-start gap-1.5 py-0.5 text-[11.5px] leading-relaxed text-[var(--warning)]">
                      <span className="mono mt-px flex-none rounded bg-white/70 px-1 text-[10px]">{i.path}</span>
                      <span>{i.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 底部操作 */}
        <div className="mt-4 flex items-center gap-2.5 border-t border-[var(--line)] pt-4">
          <button className="inline-flex h-8 items-center rounded-md border border-[var(--line-strong)] px-3.5 text-[12.5px] text-[var(--ink-2)]" onClick={onClose}>
            取消
          </button>
          <span className="ml-1 text-[10.5px] text-[var(--muted)]">若该 Agent 已有草稿，导入将覆盖它</span>
          <div className="flex-1" />
          <button
            className="inline-flex h-8 items-center gap-1.5 rounded-md bg-[var(--primary)] px-4 text-[12.5px] font-medium text-white hover:bg-[#4338CA] disabled:opacity-60"
            disabled={!canImport}
            onClick={doImport}
          >
            {busy ? '导入中…' : '导入并进入编辑'}
          </button>
        </div>
      </div>
    </div>
  )
}
