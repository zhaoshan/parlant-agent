/** 版本差异展示：DefinitionDiff → 板块级 新增/修改/删除 折叠列表；修改项展示**字段级**旧值→新值对比（发布弹窗与版本历史共用）。 */
import type { DefinitionDiff, FieldChange } from '../utils/diff'

/** 值渲染：长文本/对象收敛展示。 */
function Val({ v }: { v: unknown }) {
  if (v === undefined || v === null) return <span className="text-[var(--muted)]">∅</span>
  if (typeof v === 'string') {
    if (v.length <= 80) return <span className="whitespace-pre-wrap break-words">{v || <span className="text-[var(--muted)]">""</span>}</span>
    return (
      <div className="max-h-[72px] overflow-auto whitespace-pre-wrap break-words rounded border border-[var(--line)] bg-white/70 px-1.5 py-1">
        {v}
      </div>
    )
  }
  if (typeof v === 'boolean') return <span>{v ? 'true' : 'false'}</span>
  if (typeof v === 'number') return <span>{String(v)}</span>
  const s = JSON.stringify(v)
  return <span className="whitespace-pre-wrap break-words">{s && s.length > 140 ? `${s.slice(0, 140)}…` : s}</span>
}

function Change({ c }: { c: FieldChange }) {
  const path = c.path || '整体（结构变化）'
  return (
    <div className="mt-1.5 rounded border border-[var(--line)] bg-white/60 px-2 py-1.5">
      <div className="mono text-[10px] text-[var(--muted)]">{path}</div>
      {c.kind === 'added' && (
        <div className="mt-0.5 text-[11px] leading-relaxed text-[#059669]">
          ＋ 新增 <Val v={c.new} />
        </div>
      )}
      {c.kind === 'removed' && (
        <div className="mt-0.5 text-[11px] leading-relaxed text-[#DC2626]">
          － 删除 <Val v={c.old} />
        </div>
      )}
      {c.kind === 'modified' && (
        <div className="mt-0.5 text-[11px] leading-relaxed">
          <div className="text-[#DC2626] line-through decoration-[#FCA5A5]">
            <Val v={c.old} />
          </div>
          <div className="mt-0.5 text-[#059669]">
            <Val v={c.new} />
          </div>
        </div>
      )}
    </div>
  )
}

export function DiffList({ diff, maxHeight }: { diff: DefinitionDiff; maxHeight?: string }) {
  if (diff.same) {
    return <div className="py-2 text-center text-[12px] text-[var(--muted)]">两个版本完全一致，无差异</div>
  }
  return (
    <div className={maxHeight ? `overflow-auto ${maxHeight}` : ''}>
      {diff.sections.map((s) => (
        <details key={s.key} className="border-b border-[var(--line)] py-1 text-[11.5px] last:border-b-0" open={s.modified.length > 0}>
          <summary className="flex cursor-pointer items-center gap-2 px-1 hover:bg-[#F1F5F9]">
            <span className="font-medium text-[var(--ink)]">{s.label}</span>
            <div className="flex gap-1">
              {s.added.length > 0 && <span className="rounded bg-[#ECFDF5] px-1.5 py-0.5 text-[10px] text-[#059669]">+{s.added.length} 新增</span>}
              {s.modified.length > 0 && <span className="rounded bg-[#FFFBEB] px-1.5 py-0.5 text-[10px] text-[#B45309]">~{s.modified.length} 修改</span>}
              {s.removed.length > 0 && <span className="rounded bg-[#FEF2F2] px-1.5 py-0.5 text-[10px] text-[#DC2626]">-{s.removed.length} 删除</span>}
            </div>
          </summary>
          <div className="mt-1 flex flex-col gap-1 px-1 pb-1">
            {s.added.map((x) => <span key={`+${x}`} className="rounded bg-[#ECFDF5] px-1.5 py-0.5 text-[10.5px] text-[#059669]">＋ {x}</span>)}
            {s.removed.map((x) => <span key={`-${x}`} className="rounded bg-[#FEF2F2] px-1.5 py-0.5 text-[10.5px] text-[#DC2626]">－ {x}</span>)}
            {s.modified.map((m) => (
              <div key={`~${m.label}`} className="rounded-md border border-[#FDE68A]/70 bg-[#FFFBEB]/70 px-2 py-1.5">
                <div className="text-[11px] font-semibold text-[#B45309]">～ {m.label}</div>
                {m.changes.map((c, i) => <Change key={i} c={c} />)}
              </div>
            ))}
          </div>
        </details>
      ))}
    </div>
  )
}
