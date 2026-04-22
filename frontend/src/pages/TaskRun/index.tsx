import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { 日志地址 } from '../../api/client'
import { 获取任务, 停止任务, 重试任务, 删除任务 } from '../../api/task'
import type { 阶段记录, 任务响应 } from '../../types/task'

function 格式化时间(value: string | null | undefined) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function 格式化耗时(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  if (value < 1) return `${value.toFixed(3)} s`
  if (value < 60) return `${value.toFixed(1)} s`
  const minutes = Math.floor(value / 60)
  const seconds = value % 60
  return `${minutes} min ${seconds.toFixed(1)} s`
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

function 阶段状态文本(status: string) {
  const map: Record<string, string> = {
    pending: '等待中',
    running: '执行中',
    success: '成功',
    failed: '失败',
    stopped: '已停止',
  }
  return map[status] ?? status
}

function 状态类名(status: string) {
  if (status === 'success') return 'status-success'
  if (status === 'failed' || status === 'stopped') return 'status-failed'
  return 'status-idle'
}

function 阶段卡片类名(status: string) {
  if (status === 'success') return 'phase-card phase-card-success'
  if (status === 'failed' || status === 'stopped') return 'phase-card phase-card-failed'
  if (status === 'running') return 'phase-card phase-card-running'
  return 'phase-card'
}

const 阶段顺序 = [
  'video_extract',
  'preflight_raw',
  'colmap',
  'convert',
  'preflight_processed',
  'train',
  'render',
  'metrics',
  'report',
  'viewer',
]

const 阶段名称: Record<string, string> = {
  video_extract: '视频抽帧',
  preflight_raw: '原始数据预检查',
  colmap: 'COLMAP 重建',
  convert: '数据转换',
  preflight_processed: '训练前复检',
  train: '模型训练',
  render: '离线渲染',
  metrics: '指标评测',
  report: '结果报告',
  viewer: '启动查看器',
}

export function TaskRunPage() {
  const { taskId = '' } = useParams()
  const navigate = useNavigate()

  const [任务, set任务] = useState<任务响应 | null>(null)
  const [日志列表, set日志列表] = useState<string[]>([])
  const [错误, set错误] = useState('')
  const [提示, set提示] = useState('')
  const [加载中, set加载中] = useState(true)
  const [自动滚动, set自动滚动] = useState(true)

  const 日志容器引用 = useRef<HTMLPreElement | null>(null)

  const 已结束 = useMemo(() => {
    if (!任务) return false
    return ['success', 'failed', 'stopped', 'partial_success'].includes(任务.status)
  }, [任务])

  const 阶段列表 = useMemo(() => {
    const 已有阶段 = new Map<string, 阶段记录>()
    const history = 任务?.stage_history ?? []

    history.forEach((item) => {
      已有阶段.set(item.stage_key, item)
    })

    return 阶段顺序.map((key, index) => {
      const existed = 已有阶段.get(key)
      if (existed) return existed

      return {
        stage_key: key,
        stage_label: 阶段名称[key] ?? key,
        order: index + 1,
        status: 'pending',
        started_at: null,
        finished_at: null,
        duration_seconds: null,
        error_type: null,
        error_message: null,
      } as 阶段记录
    })
  }, [任务])

  const 当前阶段索引 = useMemo(() => {
    if (!任务?.stage_history?.length) return 0
    return Math.max(...任务.stage_history.map((item) => item.order || 0), 0)
  }, [任务])

  const 成功阶段数 = useMemo(() => {
    return 阶段列表.filter((item) => item.status === 'success').length
  }, [阶段列表])

  const 最近失败阶段 = useMemo(() => {
    const reversed = [...(任务?.stage_history ?? [])].reverse()
    return reversed.find((item) => item.status === 'failed') ?? null
  }, [任务])

  const 刷新任务 = async (静默 = false) => {
    if (!taskId) return

    try {
      if (!静默) set加载中(true)
      const data = await 获取任务(taskId)
      set任务(data)
      set错误('')
    } catch (error) {
      set错误(error instanceof Error ? error.message : '获取任务失败')
    } finally {
      if (!静默) set加载中(false)
    }
  }

  useEffect(() => {
    if (!taskId) {
      set错误('任务编号缺失')
      set加载中(false)
      return
    }
    刷新任务()
  }, [taskId])

  useEffect(() => {
    if (!taskId) return

    const ws = new WebSocket(日志地址(taskId))

    ws.onmessage = (event) => {
      const text = String(event.data ?? '').trim()
      if (!text) return
      set日志列表((prev) => [...prev, text])
    }

    ws.onerror = () => {
      // 保持静默，避免日志连接短暂波动影响页面
    }

    return () => {
      ws.close()
    }
  }, [taskId])

  useEffect(() => {
    if (!taskId || 已结束) return

    const timer = window.setInterval(() => {
      刷新任务(true)
    }, 2000)

    return () => window.clearInterval(timer)
  }, [taskId, 已结束])

  useEffect(() => {
    if (!自动滚动) return
    const el = 日志容器引用.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [日志列表, 自动滚动])

  const 执行停止 = async () => {
    if (!taskId) return

    try {
      const data = await 停止任务(taskId)
      set提示(data.message)
      await 刷新任务(true)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '停止任务失败')
    }
  }

  const 执行重试 = async () => {
    if (!taskId) return

    try {
      const data = await 重试任务(taskId)
      set提示(data.message)
      set日志列表([])
      await 刷新任务(true)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '重试任务失败')
    }
  }

  const 执行删除 = async () => {
    if (!taskId) return

    try {
      const data = await 删除任务(taskId)
      set提示(data.message)
      window.setTimeout(() => {
        navigate('/')
      }, 800)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '删除任务失败')
    }
  }

  if (加载中 && !任务) {
    return (
      <div className="page">
        <h1>任务运行</h1>
        <div className="card">正在加载任务信息…</div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>任务运行</h1>
          <p className="page-subtitle">
            本页用于展示任务运行过程，包括阶段进度、实时状态、日志输出和错误信息。
          </p>
        </div>

        <div className="inline-actions wrap-actions">
          <button className="ghost-btn" onClick={() => 刷新任务()}>
            刷新状态
          </button>

          {!已结束 ? (
            <button className="ghost-btn danger-btn" onClick={执行停止}>
              停止任务
            </button>
          ) : null}

          {任务 && ['failed', 'stopped', 'partial_success'].includes(任务.status) ? (
            <button className="ghost-btn" onClick={执行重试}>
              重试任务
            </button>
          ) : null}

          {任务 && ['success', 'partial_success', 'failed', 'stopped'].includes(任务.status) ? (
            <Link className="primary-btn" to={`/results/${taskId}`}>
              查看结果
            </Link>
          ) : null}

          {任务 && ['success', 'failed', 'stopped', 'partial_success'].includes(任务.status) ? (
            <button className="ghost-btn danger-btn" onClick={执行删除}>
              删除记录
            </button>
          ) : null}
        </div>
      </div>

      {提示 ? <div className="success-box">{提示}</div> : null}
      {错误 ? <div className="error-box">{错误}</div> : null}

      {任务 ? (
        <>
          <div className="info-grid">
            <div className="card info-card">
              <div className="meta-label">任务编号</div>
              <div className="meta-value">{任务.task_id}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">场景名称</div>
              <div className="meta-value">{任务.scene_name}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">当前状态</div>
              <div className={`status-pill ${状态类名(任务.status)}`}>
                {状态文本(任务.status)}
              </div>
            </div>
            <div className="card info-card">
              <div className="meta-label">当前阶段</div>
              <div className="meta-value">{任务.current_stage || '-'}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">重试次数</div>
              <div className="meta-value">{任务.retry_count}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">停止请求</div>
              <div className="meta-value">{任务.stop_requested ? '是' : '否'}</div>
            </div>
          </div>

          <div className="card">
            <h3>执行进度</h3>
            <p className="section-tip">
              当前进度根据任务阶段进行估算，用于反映整体执行状态。
            </p>

            <div className="progress-track">
              <div
                className="progress-bar"
                style={{
                  width: `${(成功阶段数 / Math.max(阶段列表.length, 1)) * 100}%`,
                }}
              />
            </div>

            <div className="progress-text">
              已完成 {成功阶段数} / {阶段列表.length} 个阶段，当前阶段序号 {当前阶段索引 || 0}
            </div>

            <div className="phase-grid">
              {阶段列表.map((item) => (
                <div key={item.stage_key} className={阶段卡片类名(String(item.status))}>
                  <div className="phase-order">阶段 {item.order}</div>
                  <div className="phase-title">{item.stage_label}</div>
                  <div className={`status-pill ${状态类名(String(item.status))}`}>
                    {阶段状态文本(String(item.status))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>阶段历史</h3>
            {阶段列表.length ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      {['阶段', '状态', '开始时间', '结束时间', '耗时', '错误类型', '错误信息'].map((text) => (
                        <th key={text}>{text}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {阶段列表.map((item) => (
                      <tr key={item.stage_key}>
                        <td>{item.stage_label}</td>
                        <td>{阶段状态文本(String(item.status))}</td>
                        <td>{格式化时间(item.started_at)}</td>
                        <td>{格式化时间(item.finished_at)}</td>
                        <td>{格式化耗时(item.duration_seconds)}</td>
                        <td>{item.error_type || '-'}</td>
                        <td className={item.error_message ? 'table-error-text' : ''}>
                          {item.error_message || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-tip">当前还没有阶段记录。</div>
            )}
          </div>

          {最近失败阶段 ? (
            <div className="card">
              <h3>失败信息</h3>
              <div className="details-grid">
                <div>
                  <label>失败阶段</label>
                  <div className="meta-value">{最近失败阶段.stage_label}</div>
                </div>
                <div>
                  <label>错误类型</label>
                  <div className="meta-value">{最近失败阶段.error_type || '-'}</div>
                </div>
                <div className="details-full">
                  <label>错误摘要</label>
                  <div className="error-panel">
                    {最近失败阶段.error_message || 任务.error || '-'}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <div className="card log-card">
            <div className="log-toolbar">
              <div>
                <h3 className="section-title-tight">实时日志</h3>
                <div className="section-tip">
                  日志通过 WebSocket 推送，并在运行中自动刷新任务状态。
                </div>
              </div>

              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={自动滚动}
                  onChange={(e) => set自动滚动(e.target.checked)}
                />
                <span>自动滚动</span>
              </label>
            </div>

            <pre ref={日志容器引用}>
              {日志列表.length ? 日志列表.join('\n') : '当前尚未收到日志输出。'}
            </pre>
          </div>

          <div className="card">
            <h3>时间信息</h3>
            <div className="details-grid">
              <div>
                <label>创建时间</label>
                <div className="meta-value">{格式化时间(任务.created_at)}</div>
              </div>
              <div>
                <label>开始时间</label>
                <div className="meta-value">{格式化时间(任务.started_at)}</div>
              </div>
              <div>
                <label>结束时间</label>
                <div className="meta-value">{格式化时间(任务.finished_at)}</div>
              </div>
              <div>
                <label>状态说明</label>
                <div className="meta-value">{任务.message || '-'}</div>
              </div>
            </div>
          </div>
        </>
      ) : (
        <div className="card">未找到任务信息。</div>
      )}
    </div>
  )
} 