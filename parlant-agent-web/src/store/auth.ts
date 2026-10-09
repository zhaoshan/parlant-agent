/** 认证状态：令牌 + 当前用户。token 持久化 localStorage，刷新不丢（P1 网关接入）。

- 令牌来源：登录页「IAM 账号登录」（server `POST /api/auth/login` 代理到 IAM）或
  「粘贴已有令牌」（开发/联调，token_generator.py 或 IAM 后台签发）。
- 用 `persist` 中间件：`parlant-auth` 键。登出清空并回登录页（401 拦截在 api/client request）。
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AuthUser {
  user_id: string
  user_name: string
  roles?: string[]
  permissions?: string[]
}

interface AuthState {
  token: string | null
  user: AuthUser | null
  /** 登录/粘贴令牌后写入；auth=null 表示未知（从令牌解码补全） */
  setAuth: (token: string, user?: AuthUser | null) => void
  clearAuth: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user: user ?? null }),
      clearAuth: () => set({ token: null, user: null }),
    }),
    { name: 'parlant-auth' },
  ),
)

/** 解码 JWT payload（base64url，不验签——仅用于展示/回填用户信息；验签在 server）。 */
export function decodeJwtPayload<T = Record<string, unknown>>(token: string): T | null {
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const pad = part.replace(/-/g, '+').replace(/_/g, '/')
    const b64 = pad.length % 4 ? pad.padEnd(pad.length + (4 - (pad.length % 4)), '=') : pad
    return JSON.parse(atob(b64)) as T
  } catch {
    return null
  }
}

/** 从 JWT claims 构造展示用户（sub→user_id/user_name；roles/permissions 透传）。 */
export function userFromToken(token: string): AuthUser | null {
  const claims = decodeJwtPayload<Record<string, unknown>>(token)
  if (!claims) return null
  const sub = String(claims.sub ?? claims.userId ?? '')
  if (!sub) return null
  const userName =
    String(claims.user_name ?? claims.name ?? '')
    || sub.replace(/^u-/, '')
  return {
    user_id: sub,
    user_name: userName,
    roles: (claims.roles as string[] | undefined) ?? [],
    permissions: (claims.permissions as string[] | undefined) ?? [],
  }
}