import { NavLink, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">3DGS 平台</div>
        <nav className="nav">
          <NavLink to="/">首页</NavLink>
          <NavLink to="/tasks/create">新建任务</NavLink>
          <NavLink to="/settings">系统设置</NavLink>
        </nav>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
