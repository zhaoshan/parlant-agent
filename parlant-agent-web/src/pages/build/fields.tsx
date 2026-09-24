/** Agent 构建页共享 UI：字段/输入/chips/多选下拉/段标题。 */
import { useState, type ReactNode } from 'react'
import { ChevronDown } from '../../components/Icons'

export function F({ label, hint, children, full }: { label: string; hint?: string; children: ReactNode; full?: boolean }) {
  return (
    <div className={`flex flex-col gap-1.5 ${full ? 'col-span-full' : ''}`}>
      <label className="text-[12px] font-medium text-[var(--ink-2)]">
        {label}
        {hint && <span className="ml-1.5 font-normal text-[var(--muted)]">{hint}</span>}
      </label>
      {children}
    </div>
  )
}

export const inputCls =
  'h-[32px] rounded-md border border-[var(--line-strong)] px-2.5 text-[12.5px] text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)] bg-white'

export function TextInput(props: { value?: string; onChange?: (v: string) => void; placeholder?: string; mono?: boolean; readOnly?: boolean; rows?: number }) {
  const { value = '', onChange, placeholder, mono, readOnly, rows } = props
  if (rows) {
    // 多行：不复用单行的 h-[32px]，用 rows 控制高度（min-h 保证至少多行）
    return (
      <textarea
        className={`w-full resize-y rounded-md border border-[var(--line-strong)] px-2.5 py-2 text-[12.5px] leading-relaxed text-[var(--ink)] outline-none focus:border-[var(--primary)] focus:shadow-[0_0_0_3px_var(--primary-weak)] ${mono ? 'mono text-[12px]' : ''} ${readOnly ? 'bg-[#F8FAFC] text-[var(--muted)]' : 'bg-white'}`}
        style={{ minHeight: `${rows * 20 + 16}px` }}
        rows={rows}
        value={value}
        placeholder={placeholder}
        readOnly={readOnly}
        onChange={(e) => onChange?.(e.target.value)}
      />
    )
  }
  const cls = `${inputCls} w-full ${mono ? 'mono text-[12px]' : ''} ${readOnly ? 'bg-[#F8FAFC] text-[var(--muted)]' : ''}`
  return <input className={cls} value={value} placeholder={placeholder} readOnly={readOnly} onChange={(e) => onChange?.(e.target.value)} />
}

/** 多选下拉：从已有组件中选择（用于指南绑定话术/旅程/工具等）。 */
export function MultiSelect(props: {
  label?: string
  options: { value: string; label: string }[]
  value: string[]
  onChange: (v: string[]) => void
  placeholder?: string
}) {
  const { options, value, onChange, placeholder = '从已有组件中选择', label } = props
  const [open, setOpen] = useState(false)
  const toggle = (v: string) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  return (
    <div className="relative">
      {label && <div className="mb-1.5 text-[12px] font-medium text-[var(--ink-2)]">{label}</div>}
      {/* 已选 chips + 展开按钮 */}
      <div className="flex min-h-[32px] flex-wrap items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-white px-2 py-1.5">
        {value.map((v) => {
          const opt = options.find((o) => o.value === v)
          return (
            <span key={v} className="inline-flex items-center gap-1 rounded bg-[var(--primary-weak)] px-2 py-0.5 text-[11.5px] text-[var(--primary)]">
              {opt?.label ?? v}
              <button className="cursor-pointer text-[11px]" onClick={() => toggle(v)}>×</button>
            </span>
          )
        })}
        <button className="ml-auto inline-flex cursor-pointer items-center gap-0.5 rounded border border-dashed border-[var(--line-strong)] px-1.5 py-0.5 text-[11px] text-[var(--ink-2)] hover:bg-[#F1F5F9]" onClick={(e) => { e.preventDefault(); setOpen((v) => !v) }}>
          ＋ <ChevronDown size={11} />
        </button>
      </div>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 right-0 z-50 mt-1 max-h-[220px] overflow-auto rounded-md border border-[var(--line-strong)] bg-white py-1 shadow-[0_10px_30px_rgba(15,23,42,.12)]">
            {options.length ? (
              options.map((o) => (
                <label key={o.value} className="flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-[12px] hover:bg-[var(--bg)]">
                  <input type="checkbox" checked={value.includes(o.value)} onChange={() => toggle(o.value)} className="accent-[var(--primary)]" />
                  <span className="truncate text-[var(--ink)]">{o.label}</span>
                  <span className="mono ml-auto text-[10px] text-[var(--muted)]">{o.value}</span>
                </label>
              ))
            ) : (
              <div className="px-2.5 py-2 text-[11.5px] text-[var(--muted)]">{placeholder}（当前无数据）</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export function Select(props: { value?: string; onChange?: (v: string) => void; options: { value: string; label: string }[]; className?: string }) {
  return (
    <select className={`${inputCls} cursor-pointer ${props.className ?? 'w-full'}`} value={props.value ?? ''} onChange={(e) => props.onChange?.(e.target.value)}>
      {props.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function ChipsInput(props: { value?: string[]; onChange?: (v: string[]) => void; placeholder?: string }) {
  const { value = [], onChange, placeholder } = props
  const add = (raw: string) => {
    const items = raw.split(/[,，;；]/).map((s) => s.trim()).filter(Boolean)
    onChange?.([...value, ...items])
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-[var(--line-strong)] bg-white px-2 py-1.5">
      {value.map((v, i) => (
        <span key={`${v}-${i}`} className="inline-flex items-center gap-1 rounded bg-[var(--primary-weak)] px-2 py-0.5 text-[11.5px] text-[var(--primary)]">
          {v}
          <button className="cursor-pointer text-[11px]" onClick={() => onChange?.(value.filter((_, j) => j !== i))}>×</button>
        </span>
      ))}
      <input
        className="min-w-[80px] flex-1 border-0 bg-transparent text-[12px] outline-none"
        placeholder={placeholder ?? '输入后回车'}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            add((e.target as HTMLInputElement).value)
            ;(e.target as HTMLInputElement).value = ''
          }
        }}
        onBlur={(e) => {
          if (e.target.value.trim()) {
            add(e.target.value)
            e.target.value = ''
          }
        }}
      />
    </div>
  )
}

export function Switch(props: { checked?: boolean; onChange?: (v: boolean) => void }) {
  return (
    <button
      className={`h-[18px] w-[32px] flex-none rounded-full transition ${props.checked ? 'bg-[var(--primary)]' : 'bg-[#CBD2DC]'}`}
      onClick={() => props.onChange?.(!props.checked)}
    >
      <span className={`block h-[14px] w-[14px] rounded-full bg-white transition-transform ${props.checked ? 'translate-x-[16px]' : 'translate-x-[2px]'}`} />
    </button>
  )
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-3 mt-5 border-b border-[var(--line)] pb-1.5 text-[11px] font-semibold text-[var(--ink-2)] first:mt-0">{title}</div>
      {children}
    </div>
  )
}

export function Empty({ text }: { text: string }) {
  return <div className="px-6 py-16 text-center text-[12.5px] text-[var(--muted)]">{text}</div>
}
