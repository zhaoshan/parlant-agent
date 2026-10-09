/** 路由守卫：无令牌即重定向登录页；登录后把 auth.user 同步进工作台当前用户（session 落库 user_id 用）。 */
import { useEffect, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { useApp } from '../store/app'

export default function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token)
  const user = useAuth((s) => s.user)
  const setCurrentUser = useApp((s) => s.setCurrentUser)

  useEffect(() => {
    if (user) {
      setCurrentUser({ user_id: user.user_id, user_name: user.user_name })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}