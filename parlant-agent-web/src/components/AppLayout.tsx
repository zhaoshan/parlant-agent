/** 带浅色侧栏的工作区布局（除 Agent 首页外使用）。 */
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'

export default function AppLayout() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="ml-56 flex min-w-0 flex-1 flex-col">
        <Outlet />
      </main>
    </div>
  )
}
