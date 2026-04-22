import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { 获取任务 } from '../../api/task'
import { 日志地址 } from '../../api/client'
import type { 任务响应 } from '../../types/task'

const 阶段列表 = [
  '等待启动',
  '准备配置',
  '执行预检查',
  '执行视频抽帧',
  '执行 COLMAP',
  '执行转换',
  '训练前复检',
  '执行训练',
  '执行渲染',
  '执行评测',
  '启动查看器',
  '已完成',
]

function 推断进度(task: 任务响应 | null) {
  if (!task) return 0
  if (task.status === 'success') return 100
  if (task.status === 'failed') return 100

  const index = 阶段列表.findIndex((item) => item === task.current_stage)
  if (index < 0) return task.status === 'queued' ? 6 : 10
  return Math.max(6, Math.round(((index + 1) / 阶段列表.length) * 100))
}

function 获取阶段状态(label: string, current: string, status?: string) {
  const currentIndex = 阶段列表.findIndex((item) => item === current)
  const selfIndex = 阶段列表.findIndex((item) => item === label)

  if (status === 'success') return 'done'
  if (status === 'failed' && selfIndex === currentIndex) return 'failed'
  if (selfIndex < currentIndex) return 'done'
  if (selfIndex === currentIndex) return 'active'
  return 'pending'
}

function 日志级别(text: string) {
  const line = text.toLowerCase()
  if (line.includes('error') || line.includes('traceback') || line.includes('失败')) {
    return 'error'
  }
  if (line.includes('warning') || line.includes('warn') || line.includes('警告')) {
    return 'warning'
  }
  if (line.includes('success') || line.includes('完成') || line.includes('done')) {
    return 'success'
  }
  return 'normal'
}

export function TaskRunPage() {
  const { taskId = '' } = useParams()
  const [任务, set任务] = useState<任务响应 | null>(null)
  const [日志, set日志] = useState<string[]>([])
  const [错误, set错误] = useState('')
  const [自动滚动, set自动滚动] = useState(true)
  const 日志容器引用 = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!taskId) return

    let active = true
    const 拉取一次 = async () => {
      try {
        const data = await 获取任务(taskId)
        if (!active) return
        set任务(data)
      } catch (error) {
        if (!active) return
        set错误(error instanceof Error ? error.message : '获取状态失败')
      }
    }

    拉取一次()
    const timer = window.setInterval(拉取一次, 2000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [taskId])

  useEffect(() => {
    if (!taskId) return

    let active = true
    const ws = new WebSocket(日志地址(taskId))

    ws.onopen = () => {
      if (!active) return
      set错误('')
      ws.send('ping')
    }

    ws.onmessage = (event) => {
      if (!active) return
      set日志((prev) => [...prev, String(event.data)])

      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }

    ws.onerror = () => {
      if (!active) return
      if (任务?.status !== 'success' && 任务?.status !== 'failed') {
        set错误('日志连接异常')
      }
    }

    ws.onclose = () => {
      if (!active) return
      if (任务?.status === 'success' || 任务?.status === 'failed') {
        set错误('')
      }
    }

    return () => {
      active = false
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  }, [taskId, 任务?.status])

  useEffect(() => {
    if (!自动滚动 || !日志容器引用.current) return
    日志容器引用.current.scrollTop = 日志容器引用.current.scrollHeight
  }, [日志, 自动滚动])

  const 是否成功 = useMemo(() => 任务?.status === 'success', [任务])
  const 是否结束 = useMemo(
    () => 任务?.status === 'success' || 任务?.status === 'failed',
    [任务],
  )
  const 进度值 = useMemo(() => 推断进度(任务), [任务])
  const 最近错误日志 = useMemo(
    () => [...日志].reverse().find((item) => 日志级别(item) === 'error') || '',
    [日志],
  )

  return (
    <div className="page task-run-page">
      <div className="page-header">
        <div>
          <h1>任务运行</h1>
          <p className="page-subtitle">
            本页用于展示任务运行过程，包括阶段进度、实时状态、日志输出和错误信息。
          </p>
        </div>
        <div className="inline-actions wrap-actions">
          <button className="ghost-btn" onClick={() => window.location.reload()}>
            刷新页面
          </button>
          <label className="toggle-item small-toggle-item">
            <input
              type="checkbox"
              checked={自动滚动}
              onChange={(e) => set自动滚动(e.target.checked)}
            />
            <span>日志自动滚动</span>
          </label>
        </div>
      </div>

      <div className="card-grid">
        <div className="card compact-card">
          <h3>任务编号</h3>
          <p className="mono-text">{taskId || '无'}</p>
        </div>
        <div className="card compact-card">
          <h3>状态</h3>
          <span
            className={`status-pill ${任务?.status === 'success'
                ? 'status-success'
                : 任务?.status === 'failed'
                  ? 'status-failed'
                  : 'status-idle'
              }`}
          >
            {任务?.status || '加载中'}
          </span>
        </div>
        <div className="card compact-card">
          <h3>当前阶段</h3>
          <p>{任务?.current_stage || '等待中'}</p>
        </div>
        <div className="card compact-card">
          <h3>进度估计</h3>
          <p>{进度值}%</p>
        </div>
      </div>

      <div className="card">
        <div className="toolbar-row">
          <div>
            <h3>执行进度</h3>
            <p className="section-tip">
              当前进度根据任务阶段进行估算，用于反映整体执行状态。
            </p>
          </div>
          <div className="progress-text">{任务?.message || '正在获取任务信息'}</div>
        </div>

        <div className="progress-track">
          <div className="progress-bar" style={{ width: `${进度值}%` }} />
        </div>

        <div className="stage-grid">
          {阶段列表.map((item) => {
            const state = 获取阶段状态(item, 任务?.current_stage || '', 任务?.status)
            return (
              <div key={item} className={`stage-chip stage-${state}`}>
                <span className="stage-dot" />
                <span>{item}</span>
              </div>
            )
          })}
        </div>
      </div>

      {任务?.status === 'failed' ? (
        <div className="error-box">
          <strong>任务执行失败：</strong>
          <div>失败阶段：{任务.current_stage || '未知阶段'}</div>
          <div>后端信息：{任务.error || 任务.message || '无'}</div>
          {最近错误日志 ? <div>最近错误日志：{最近错误日志}</div> : null}
        </div>
      ) : null}

      {错误 ? <div className="error-box">{错误}</div> : null}

      <div className="card log-card">
        <div className="toolbar-row">
          <div>
            <h3>实时日志</h3>
            <p className="section-tip">
              红色为错误，橙色为警告，绿色为完成提示。
            </p>
          </div>
          <div className="meta-label">共 {日志.length} 行</div>
        </div>

        <div className="log-stream" ref={日志容器引用}>
          {日志.length ? (
            日志.map((line, index) => (
              <div key={`${index}-${line}`} className={`log-line log-${日志级别(line)}`}>
                {line}
              </div>
            ))
          ) : (
            <div className="empty-log">等待日志输出……</div>
          )}
        </div>
      </div>

      <div className="inline-actions wrap-actions">
        {是否成功 ? (
          <Link className="primary-btn" to={`/results/${taskId}`}>
            查看结果
          </Link>
        ) : null}
        {是否结束 ? (
          <Link className="ghost-btn" to="/tasks/create">
            返回新建任务
          </Link>
        ) : null}
      </div>
    </div>
  )
}
