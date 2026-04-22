import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { 获取任务列表 } from '../../api/task'
import type { 任务响应 } from '../../types/task'

function 格式化时间(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function 状态文本(status: string) {
  const map: Record<string, string> = {
    created: '已创建',
    queued: '排队中',
    running: '运行中',
    stopping: '停止中',
    stopped: '已停止',
    success: '已完成',
    failed: '失败',
    retrying: '重试中',
    partial_success: '部分完成',
  }
  return map[status] ?? status
}

function 状态类名(status: string) {
  if (status === 'success') return 'status-success'
  if (status === 'failed' || status === 'stopped') return 'status-failed'
  return 'status-idle'
}

export function HomePage() {
  const [任务列表, set任务列表] = useState<任务响应[]>([])
  const [加载中, set加载中] = useState(true)
  const [错误, set错误] = useState('')

  const 刷新任务列表 = async () => {
    try {
      set加载中(true)
      const items = await 获取任务列表()

      const sorted = [...items].sort((a, b) => {
        const aTime = new Date(a.created_at || 0).getTime()
        const bTime = new Date(b.created_at || 0).getTime()
        return bTime - aTime
      })

      set任务列表(sorted.slice(0, 8))
      set错误('')
    } catch (error) {
      set错误(error instanceof Error ? error.message : '获取任务列表失败')
    } finally {
      set加载中(false)
    }
  }

  useEffect(() => {
    刷新任务列表()
  }, [])

  const 统计信息 = useMemo(() => {
    const total = 任务列表.length
    const running = 任务列表.filter((item) =>
      ['running', 'queued', 'retrying', 'stopping'].includes(item.status),
    ).length
    const success = 任务列表.filter((item) => item.status === 'success').length
    const failed = 任务列表.filter((item) =>
      ['failed', 'stopped', 'partial_success'].includes(item.status),
    ).length

    return { total, running, success, failed }
  }, [任务列表])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>三维重建平台</h1>
          <p className="page-subtitle">
            本系统采用前后端分离架构，由前端界面、后端服务和重建引擎组成，支持任务配置、流程调度、日志查看与结果展示。
          </p>
        </div>
        <div className="inline-actions wrap-actions">
          <button type="button" className="ghost-btn" onClick={刷新任务列表}>
            刷新首页
          </button>
          <Link className="primary-btn" to="/tasks/create">
            创建任务
          </Link>
        </div>
      </div>

      {错误 ? <div className="error-box">{错误}</div> : null}

      <div className="card-grid">
        <div className="card">
          <h3>前端界面</h3>
          <p className="section-tip">提供参数配置、任务创建、运行监控和结果展示功能。</p>
        </div>
        <div className="card">
          <h3>后端服务</h3>
          <p className="section-tip">负责任务创建、状态管理、配置生成和日志推送。</p>
        </div>
        <div className="card">
          <h3>重建引擎</h3>
          <p className="section-tip">集成 COLMAP、数据转换、模型训练、渲染、评测与查看器功能。</p>
        </div>
      </div>

      <div className="info-grid">
        <div className="card info-card">
          <div className="meta-label">最近任务数</div>
          <div className="meta-value">{统计信息.total}</div>
        </div>
        <div className="card info-card">
          <div className="meta-label">运行中</div>
          <div className="meta-value">{统计信息.running}</div>
        </div>
        <div className="card info-card">
          <div className="meta-label">已完成</div>
          <div className="meta-value">{统计信息.success}</div>
        </div>
        <div className="card info-card">
          <div className="meta-label">失败/已停止</div>
          <div className="meta-value">{统计信息.failed}</div>
        </div>
      </div>

      <div className="card">
        <div className="toolbar-row">
          <div>
            <h3>最近任务</h3>
            <p className="section-tip">展示最近创建的任务，可快速跳转到运行页或结果页。</p>
          </div>
        </div>

        {加载中 ? (
          <div className="empty-tip">正在加载最近任务…</div>
        ) : !任务列表.length ? (
          <div className="empty-tip">当前还没有任务记录，先创建一个任务试试。</div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>任务编号</th>
                  <th>场景名称</th>
                  <th>当前状态</th>
                  <th>当前阶段</th>
                  <th>创建时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {任务列表.map((item) => (
                  <tr key={item.task_id}>
                    <td>{item.task_id}</td>
                    <td>{item.scene_name}</td>
                    <td>
                      <span className={`status-pill ${状态类名(item.status)}`}>
                        {状态文本(item.status)}
                      </span>
                    </td>
                    <td>{item.current_stage || '-'}</td>
                    <td>{格式化时间(item.created_at)}</td>
                    <td>
                      <div className="inline-actions wrap-actions">
                        <Link className="ghost-btn" to={`/tasks/${item.task_id}`}>
                          运行页
                        </Link>
                        <Link className="ghost-btn" to={`/results/${item.task_id}`}>
                          结果页
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

