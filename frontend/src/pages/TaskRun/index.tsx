import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { 获取任务 } from '../../api/task'
import { 日志地址 } from '../../api/client'
import type { 任务响应 } from '../../types/task'

export function TaskRunPage() {
  const { taskId = '' } = useParams()
  const [任务, set任务] = useState<任务响应 | null>(null)
  const [日志, set日志] = useState<string[]>([])
  const [错误, set错误] = useState('')

  useEffect(() => {
    if (!taskId) return
    const timer = window.setInterval(async () => {
      try {
        const data = await 获取任务(taskId)
        set任务(data)
      } catch (error) {
        set错误(error instanceof Error ? error.message : '获取状态失败')
      }
    }, 2000)

    return () => window.clearInterval(timer)
  }, [taskId])

  useEffect(() => {
    if (!taskId) return
    const ws = new WebSocket(日志地址(taskId))
    ws.onopen = () => ws.send('连接成功')
    ws.onmessage = (event) => {
      set日志((prev) => [...prev, event.data])
      ws.send('继续')
    }
    ws.onerror = () => set错误('日志连接异常')
    return () => ws.close()
  }, [taskId])

  const 是否完成 = useMemo(() => 任务?.status === 'success', [任务])

  return (
    <div className="page">
      <h1>任务运行</h1>
      <div className="card-grid">
        <div className="card">
          <h3>任务编号</h3>
          <p>{taskId || '无'}</p>
        </div>
        <div className="card">
          <h3>状态</h3>
          <p>{任务?.status || '加载中'}</p>
        </div>
        <div className="card">
          <h3>当前阶段</h3>
          <p>{任务?.current_stage || '等待中'}</p>
        </div>
      </div>

      <div className="card">
        <h3>状态说明</h3>
        <p>{任务?.message || '正在获取任务信息'}</p>
      </div>

      <div className="card log-card">
        <h3>实时日志</h3>
        <pre>{日志.length ? 日志.join('\n') : '等待日志输出……'}</pre>
      </div>

      {错误 ? <div className="error-box">{错误}</div> : null}

      {是否完成 ? (
        <Link className="primary-btn" to={`/results/${taskId}`}>
          查看结果
        </Link>
      ) : null}
    </div>
  )
}
