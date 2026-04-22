import { Link } from 'react-router-dom'

export function HomePage() {
  return (
    <div className="page">
      <h1>三维重建平台</h1>
      <p>
        本系统采用前后端分离架构，由前端界面、后端服务和重建引擎组成，
        支持任务配置、流程调度、日志查看与结果展示。
      </p>

      <div className="card-grid">
        <div className="card">
          <h3>前端界面</h3>
          <p>提供参数配置、任务创建、运行监控和结果展示功能。</p>
        </div>
        <div className="card">
          <h3>后端服务</h3>
          <p>负责任务创建、状态管理、配置生成和日志推送。</p>
        </div>
        <div className="card">
          <h3>重建引擎</h3>
          <p>集成 COLMAP、数据转换、模型训练、渲染、评测与查看器功能。</p>
        </div>
      </div>

      <Link className="primary-btn" to="/tasks/create">
        创建任务
      </Link>
    </div>
  )
}