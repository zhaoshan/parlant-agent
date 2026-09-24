/** 基础信息（全宽表单）—— agent 元数据。 */
import { useBuild } from '../../store/build'
import { ChipsInput, F, Section, Select, TextInput } from './fields'

export default function Basics() {
  const { definition, update } = useBuild()
  if (!definition) return null
  const a = definition.agent
  return (
    <div className="max-w-[680px] flex-1 overflow-y-auto p-5">
      <Section title="身份">
        <div className="grid grid-cols-2 gap-4">
          <F label="Agent 名称" full>
            <TextInput value={a.name} onChange={(v) => update((d) => (d.agent.name = v))} />
          </F>
          <F label="Agent ID" hint="唯一键，不可修改">
            <TextInput value={a.id} readOnly mono />
          </F>
          <F label="版本">
            <TextInput value={a.version} readOnly mono />
          </F>
          <F label="默认语言">
            <Select value={a.default_language ?? 'zh-CN'} onChange={(v) => update((d) => (d.agent.default_language = v))} options={[{ value: 'zh-CN', label: '中文 zh-CN' }, { value: 'en-US', label: 'English en-US' }]} />
          </F>
        </div>
        <div className="mt-4">
          <F label="描述" hint="身份与职责，塑造 Agent 行为">
            <TextInput rows={3} value={a.description ?? ''} onChange={(v) => update((d) => (d.agent.description = v))} />
          </F>
        </div>
      </Section>

      <Section title="标签与组合模式">
        <div className="grid grid-cols-2 gap-4">
          <F label="标签 Tags">
            <ChipsInput value={a.tags ?? []} onChange={(v) => update((d) => (d.agent.tags = v))} />
          </F>
          <F label="组合模式" hint="话术/指南如何与 AI 生成拼接">
            <Select
              value={a.composition_mode ?? 'fluid'}
              onChange={(v) => update((d) => (d.agent.composition_mode = v))}
              options={[
                { value: 'fluid', label: 'fluid · 流畅（话术优先，可拼装）' },
                { value: 'strict', label: 'strict · 严格（完整引用话术）' },
                { value: 'loose', label: 'loose · 松散（AI 自由发挥）' },
              ]}
            />
          </F>
        </div>
      </Section>
    </div>
  )
}
