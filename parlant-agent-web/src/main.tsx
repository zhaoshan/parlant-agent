/** AgentStudio 路由：首页无侧栏；其余在 AppLayout（浅色侧栏）内。 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import AppLayout from './components/AppLayout'
import Build from './pages/Build'
import Home from './pages/Home'
import Observability from './pages/Observability'
import Placeholder from './pages/Placeholder'
import Settings from './pages/Settings'
import Simulate from './pages/Simulate'
import Versions from './pages/Versions'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        {/* Agent 首页：无侧栏 */}
        <Route path="/" element={<Home />} />
        {/* 带侧栏 */}
        <Route element={<AppLayout />}>
          <Route path="/build" element={<Build />} />
          <Route path="/build/versions" element={<Versions />} />
          {/* 预留功能：技能市场（阶段7 技能平台）、渠道部署（阶段5 §5.8） */}
          <Route
            path="/skills"
            element={<Placeholder title="技能市场" desc="技能插件的安装、配置与编排（预留 · 规划见 plan/阶段7-技能平台）" backTo="/build" backLabel="返回 Agent 构建" />}
          />
          <Route
            path="/deploy"
            element={<Placeholder title="渠道部署" desc="版本 × 渠道部署矩阵：钉钉 / 飞书 / web widget 接入（预留 · 规划见 plan/阶段5 §5.8）" backTo="/build" backLabel="返回 Agent 构建" />}
          />
          <Route path="/simulate" element={<Simulate />} />
          <Route
            path="/auto-sim"
            element={<Placeholder title="自动仿真" desc="仿真脚本 + 执行记录（阶段6）" backTo="/simulate" />}
          />
          <Route
            path="/obs"
            element={<Observability />}
          />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Home />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
