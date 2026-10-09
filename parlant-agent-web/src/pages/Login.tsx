/** 登录页（无侧栏）：IAM 账号登录 或 粘贴已有令牌（开发/联调）。 */
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuth, userFromToken } from '../store/auth'

export default function Login() {
  const navigate = useNavigate()
  const setAuth = useAuth((s) => s.setAuth)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [paste, setPaste] = useState('')
  const [iamOpen, setIamOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const r = await authApi.login(username, password)
      setAuth(r.access_token, r.user ?? null)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  const onPaste = () => {
    const token = paste.trim()
    if (!token) {
      setError('请先粘贴令牌')
      return
    }
    const user = userFromToken(token)
    if (!user) {
      setError('令牌解析失败：不是合法的 JWT（应形如 eyJ...eyJ...signature 三段）')
      return
    }
    setError(null)
    setAuth(token, user)
    navigate('/', { replace: true })
  }

  return (
    <div className="grid min-h-screen place-items-center bg-[var(--bg)] px-4">
      <div className="w-full max-w-sm">
        {/* 品牌 */}
        <div className="mb-6 flex items-center justify-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-[var(--primary)] text-lg font-bold text-white">
            P
          </div>
          <div>
            <div className="text-lg font-semibold text-[var(--ink)]">AgentStudio</div>
            <div className="text-[12px] text-[var(--muted)]">Parlant 客服智能体工作台</div>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[12.5px] leading-snug text-rose-700">
            {error}
          </div>
        )}

        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-6 shadow-sm">
          {/* 默认折叠成卡片的 IAM 登录 / 粘贴令牌两个入口 */}
          <button
            type="button"
            onClick={() => setIamOpen(true)}
            className="mb-3 w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-4 py-3 text-left text-[13px] font-medium text-[var(--ink)] hover:border-[var(--primary)] hover:shadow-sm"
          >
            使用 IAM 账号登录
            <span className="mt-0.5 block text-[11px] font-normal text-[var(--muted)]">
              通过统一身份认证（unify IAM）获取工作台令牌
            </span>
          </button>

          {!iamOpen && (
            <button
              type="button"
              onClick={() => document.getElementById('paste-token')?.focus()}
              className="w-full rounded-lg border border-dashed border-[var(--line-strong)] px-4 py-3 text-left text-[13px] font-medium text-[var(--ink)] hover:bg-[var(--bg)]"
            >
              粘贴已有令牌
              <span className="mt-0.5 block text-[11px] font-normal text-[var(--muted)]">
                开发/联调：粘贴 server `test/token_generator.py` 或 IAM 后台签发的 access_token
              </span>
            </button>
          )}

          {/* 粘贴令牌输入（始终可见，开发联调主入口） */}
          <div className="mt-3">
            <label htmlFor="paste-token" className="mb-1.5 block text-[12px] font-medium text-[var(--ink-2)]">
              access_token
            </label>
            <div className="flex gap-2">
              <input
                id="paste-token"
                value={paste}
                onChange={(e) => setPaste(e.target.value)}
                placeholder="eyJhbGciOiJSUzI1NiIs..."
                autoComplete="off"
                spellCheck={false}
                className="mono min-h-11 flex-1 rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 text-[12px] text-[var(--ink)] outline-none placeholder:text-[var(--muted)] focus:border-[var(--primary)]"
              />
              <button
                type="button"
                onClick={onPaste}
                className="grid min-h-11 min-w-24 place-items-center rounded-lg bg-[var(--primary)] px-4 text-[13px] font-medium text-white hover:brightness-105"
              >
                进入
              </button>
            </div>
          </div>

          {/* IAM 账号登录表单（主入口，展开后替代上方按钮） */}
          {iamOpen && (
            <form onSubmit={onSubmit} className="mt-5 border-t border-[var(--line)] pt-5">
              <div className="mb-3">
                <label htmlFor="username" className="mb-1.5 block text-[12px] font-medium text-[var(--ink-2)]">
                  用户名
                </label>
                <input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoComplete="username"
                  className="min-h-11 w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 text-[13px] text-[var(--ink)] outline-none placeholder:text-[var(--muted)] focus:border-[var(--primary)]"
                  placeholder="IAM 用户名"
                />
              </div>
              <div className="mb-5">
                <label htmlFor="password" className="mb-1.5 block text-[12px] font-medium text-[var(--ink-2)]">
                  密码
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
                  className="min-h-11 w-full rounded-lg border border-[var(--line)] bg-[var(--bg)] px-3 text-[13px] text-[var(--ink)] outline-none placeholder:text-[var(--muted)] focus:border-[var(--primary)]"
                  placeholder="••••••••"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className={`flex min-h-11 w-full items-center justify-center gap-2 rounded-lg text-[13px] font-medium text-white ${
                  loading ? 'bg-[var(--primary)] opacity-60' : 'bg-[var(--primary)] hover:brightness-105'
                }`}
              >
                {loading ? '登录中…' : '登录'}
              </button>
              <button
                type="button"
                onClick={() => setIamOpen(false)}
                className="mt-2 w-full py-1.5 text-[12px] text-[var(--muted)] hover:text-[var(--ink-2)]"
              >
                ← 收起表单，改用粘贴令牌
              </button>
            </form>
          )}
        </div>

        <p className="mt-4 text-center text-[11px] leading-relaxed text-[var(--muted)]">
          令牌只存于浏览器 localStorage；请求经 server 代理，IAM 私钥不出内网。
          <br />IAM 未配置时仅「粘贴令牌」可用（server .env 设 <span className="mono">AUTH_MODE=jwt/gateway</span>）。
        </p>
      </div>
    </div>
  )
}