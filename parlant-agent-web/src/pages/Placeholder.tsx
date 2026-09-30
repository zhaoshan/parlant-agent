/** 通用占位页（阶段3 后续实现：构建/版本/追踪/自动仿真/设置；以及预留菜单：技能市场/渠道部署）。 */
import { useNavigate } from 'react-router-dom'

export default function Placeholder({ title, desc, backTo = '/simulate', backLabel = '返回模拟对话' }: { title: string; desc: string; backTo?: string; backLabel?: string }) {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-[52px] flex-none items-center border-b border-[var(--line)] bg-[var(--surface)] px-6">
        <div className="text-[13px] text-[var(--muted)]">{title}</div>
      </div>
      <div className="mx-auto max-w-[820px] flex-1 px-7 pt-16 text-center">
        <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl bg-[#F1F5F9] text-[var(--muted)]">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8h.01M11 12h1v4h1" />
          </svg>
        </div>
        <div className="text-[13px] font-medium text-[var(--ink-2)]">{title}</div>
        <div className="mt-1.5 text-[12px] text-[var(--muted)]">{desc}</div>
        <button
          className="mt-5 inline-flex h-8 items-center rounded-md border border-[var(--line-strong)] bg-[var(--surface)] px-4 text-[12.5px] text-[var(--ink-2)] hover:bg-[#F1F5F9]"
          onClick={() => navigate(backTo)}
        >
          {backLabel}
        </button>
      </div>
    </div>
  )
}
