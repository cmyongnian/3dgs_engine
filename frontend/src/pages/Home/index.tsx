import { Link } from 'react-router-dom'

export function HomePage() {
  return (
    <div className="page">
      <h1>三维重建平台前后端分离版</h1>
      <p>这一版结构已经按标准拆成前端、后端、引擎三层，适合后续继续扩展图形化界面和任务管理。</p>
      <div className="card-grid">
        <div className="card">
          <h3>前端</h3>
          <p>参数配置、任务运行、日志查看、结果展示。</p>
        </div>
        <div className="card">
          <h3>后端</h3>
          <p>任务创建、运行时配置生成、状态管理、日志推送。</p>
        </div>
        <div className="card">
          <h3>引擎</h3>
          <p>保留你现有的 COLMAP、转换、训练、渲染、评测、查看器能力。</p>
        </div>
      </div>
      <Link className="primary-btn" to="/tasks/create">
        去创建任务
      </Link>
    </div>
  )
}
