/** 内联 SVG 图标（Lucide 风格，stroke 1.8，16px 基准） */
import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement> & { size?: number }

function base({ size = 15, ...rest }: P) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    ...rest,
  }
}

export const HomeIcon = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
  </svg>
)

export const BuildIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
)

export const ChatIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  </svg>
)

export const AutoIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M21 12a9 9 0 1 1-2.64-6.36L21 8" />
    <path d="M21 3v5h-5" />
  </svg>
)

export const PulseIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 3v18h18" />
    <path d="M7 15l4-6 4 3 5-7" />
  </svg>
)

export const GearIcon = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19 12a7 7 0 0 1-.4 2.4l2 1.6-2 3.4-2.4-.9a7 7 0 0 1-2.1 1.2L13.7 22h-3.4l-.4-2.3a7 7 0 0 1-2.1-1.2l-2.4.9-2-3.4 2-1.6A7 7 0 0 1 5 12c0-.8.14-1.6.4-2.4l-2-1.6 2-3.4 2.4.9a7 7 0 0 1 2.1-1.2L10.3 2h3.4l.4 2.3a7 7 0 0 1 2.1 1.2l2.4-.9 2 3.4-2 1.6c.26.8.4 1.6.4 2.4z" />
  </svg>
)

export const TraceIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
  </svg>
)

export const ToolIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
)

export const ChevronDown = (p: P) => (
  <svg {...base(p)}>
    <path d="M6 9l6 6 6-6" />
  </svg>
)

export const SendIcon = (p: P) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
  </svg>
)

/** 技能市场：插件包（box） */
export const MarketIcon = (p: P) => (
  <svg {...base(p)}>
    <path d="M21 8l-9-5-9 5v8l9 5 9-5z" />
    <path d="M3 8l9 5 9-5" />
    <path d="M12 13v8" />
  </svg>
)

/** 渠道部署：广播触达（broadcast） */
export const DeployIcon = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="1.6" />
    <path d="M8.6 8.6a4.8 4.8 0 0 0 0 6.8M15.4 8.6a4.8 4.8 0 0 1 0 6.8" />
    <path d="M5.8 5.8a8.7 8.7 0 0 0 0 12.4M18.2 5.8a8.7 8.7 0 0 1 0 12.4" />
  </svg>
)
