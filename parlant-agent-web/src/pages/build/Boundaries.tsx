/** 边界与开场白（全宽表单）—— allowed/prohibited/紧急兜底/开场白/超时兜底。 */
import { useBuild } from '../../store/build'
import { F, Section, TextInput } from './fields'

function StringList(props: { value: string[]; onChange: (v: string[]) => void; placeholder: string; addLabel: string }) {
  const { value, onChange, placeholder, addLabel } = props
  const add = () => onChange([...value, ''])
  const set = (i: number, v: string) => onChange(value.map((x, j) => (j === i ? v : x)))
  const del = (i: number) => onChange(value.filter((_, j) => j !== i))
  return (
    <div className="flex flex-col gap-2">
      {value.map((item, i) => (
        <div key={i} className="flex items-center gap-2">
          <TextInput value={item} onChange={(v) => set(i, v)} placeholder={placeholder} />
          <button className="h-8 w-8 flex-none cursor-pointer rounded-md text-[var(--muted)] hover:bg-[#FEF2F2] hover:text-[var(--danger)]" onClick={() => del(i)}>✕</button>
        </div>
      ))}
      <button className="inline-flex h-7 items-center justify-self-start rounded-md border border-dashed border-[var(--line-strong)] px-2.5 text-[11.5px] text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={add}>
        ＋ {addLabel}
      </button>
    </div>
  )
}

export default function Boundaries() {
  const { definition, update } = useBuild()
  if (!definition) return null
  const a = definition.agent
  const b = a.boundary ?? { allowed: [], prohibited: [], emergency_action: '' }
  const u = a.utterances ?? {}
  const setBoundary = (patch: Partial<typeof b>) => update((d) => (d.agent.boundary = { ...b, ...patch }))
  const setUtterance = (patch: Partial<typeof u>) => update((d) => (d.agent.utterances = { ...u, ...patch }))

  return (
    <div className="max-w-[680px] flex-1 overflow-y-auto p-5">
      <Section title="边界 · 允许 / 禁止">
        <div className="grid grid-cols-2 gap-5">
          <F label="允许 Allowed" hint="Agent 可以执行的职责范围">
            <StringList value={b.allowed ?? []} onChange={(v) => setBoundary({ allowed: v })} placeholder="如：提前结清办理、余额查询" addLabel="添加允许项" />
          </F>
          <F label="禁止 Prohibited" hint="明确不执行的行为">
            <StringList value={b.prohibited ?? []} onChange={(v) => setBoundary({ prohibited: v })} placeholder="如：办理其他贷款业务、承诺利率" addLabel="添加禁止项" />
          </F>
        </div>
      </Section>

      <Section title="紧急兜底">
        <F label="紧急动作 Emergency Action" hint="遇到无法处理/边界情况时的兜底行为">
          <TextInput rows={2} value={b.emergency_action ?? ''} onChange={(v) => setBoundary({ emergency_action: v })} />
        </F>
      </Section>

      <Section title="开场白 Utterances">
        <F label="开场白 Greeting" hint="新会话首次回复模板（可多条）">
          <StringList value={u.greeting ?? []} onChange={(v) => setUtterance({ greeting: v })} placeholder="如：您好，我是提前结清助手，很高兴为您服务" addLabel="添加开场白" />
        </F>
        <div className="mt-5 grid grid-cols-2 gap-4">
          <F label="超时兜底 Timeout Fallback">
            <TextInput rows={2} value={u.timeout_fallback ?? ''} onChange={(v) => setUtterance({ timeout_fallback: v })} />
          </F>
          <F label="系统错误兜底 Error Fallback">
            <TextInput rows={2} value={u.system_error_fallback ?? ''} onChange={(v) => setUtterance({ system_error_fallback: v })} />
          </F>
        </div>
      </Section>
    </div>
  )
}
