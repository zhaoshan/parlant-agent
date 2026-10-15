/** 启动鉴权分流（doc11 形态 B，替代原登录页）：
 *  - 已有会话（含 dev 占位）→ 放行；
 *  - URL 带 `?access_token=`（IAM hub 回跳）→ 收 token、清 URL、进；
 *  - 否则拉 `GET /api/auth/mode`：`dev` → 写占位会话直进；`gateway` → 跳 IAM hub 登录。
 *  作为根路由包装：bootstrap 完成前渲染占位，避免子路由在未定态下发请求。
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useApp } from '../store/app'
import { devSession, useAuth, userFromToken } from '../store/auth'

export default function AuthBootstrap({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const setCurrentUser = useApp((s) => s.setCurrentUser)
  const [booted, setBooted] = useState(() => Boolean(useAuth.getState().token))

  // 登录态确立后同步工作台当前用户（session 落库 user_id 用；替代原 RequireAuth 职责）
  useEffect(() => {
    if (user) setCurrentUser({ user_id: user.user_id, user_name: user.user_name })
  }, [user, setCurrentUser])

  useEffect(() => {
    if (useAuth.getState().token) {
      // 已登录（含 dev 占位）→ 放行
      setBooted(true)
      return
    }
    const run = async () => {
      // ① IAM hub 回跳：URL 带 ?access_token → 收 token、清地址栏、进
      //    （doc11 附录A 项①：若 hub 一并交付 ?refresh_token 则存下，供 401 静默刷新）
      const params = new URLSearchParams(window.location.search)
      const urlToken = params.get('access_token')
      if (urlToken) {
        useAuth.getState().setAuth(urlToken, userFromToken(urlToken), params.get('refresh_token'))
        window.history.replaceState(null, '', window.location.pathname)
        setBooted(true)
        navigate('/', { replace: true })
        return
      }
      // ② 无 token、非回跳 → 按 server 认证模式分流
      try {
        const m = await authApi.mode()
        if (m.mode === 'dev') {
          devSession()
        } else if (m.mode === 'gateway') {
          const hub = m.hub_base || ''
          if (hub) {
            const returnTo = encodeURIComponent(`${window.location.origin}/`)
            // app=parlant-agent-server：让 hub 的「企业组织」下拉只显示启用了 parlant 的租户
            // （iam_tenant_application 管控，IAM /auth/sso/tenants?app_code= 过滤）
            window.location.href = `${hub}/login?return_to=${returnTo}&app=parlant-agent-server`
          }
          // hub_base 未配：不放行会死等 → 落到下面 setBooted(true)，靠首请求 401 再兜底跳 '/'（client.ts）
        }
      } catch {
        /* mode 端点不可达：dev 下 server 仍全放行，放行让首请求定 401/200 */
      }
      setBooted(true)
    }
    run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate])

  if (!booted) {
    return (
      <div className="grid min-h-screen place-items-center bg-[var(--bg)] text-[13px] text-[var(--muted)]">
        正在进入…
      </div>
    )
  }
  return <>{children}</>
}