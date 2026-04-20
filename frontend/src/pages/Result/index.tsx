import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { 获取结果 } from '../../api/task'

export function ResultPage() {
  const { taskId = '' } = useParams()
  const [数据, set数据] = useState<{ task_id: string; status: string; scene_name: string; result: Record<string, string>; error?: string | null } | null>(null)
  const [错误, set错误] = useState('')

  useEffect(() => {
    if (!taskId) return
    获取结果(taskId)
      .then(set数据)
      .catch((error) => set错误(error instanceof Error ? error.message : '获取结果失败'))
  }, [taskId])

  return (
    <div className="page">
      <h1>任务结果</h1>
      {错误 ? <div className="error-box">{错误}</div> : null}
      <div className="card-grid">
        <div className="card">
          <h3>任务状态</h3>
          <p>{数据?.status || '加载中'}</p>
        </div>
        <div className="card">
          <h3>场景名称</h3>
          <p>{数据?.scene_name || '加载中'}</p>
        </div>
      </div>
      <div className="card">
        <h3>输出目录</h3>
        <p>{数据?.result?.output_dir || '暂无'}</p>
      </div>
      <div className="card">
        <h3>日志目录</h3>
        <p>{数据?.result?.log_dir || '暂无'}</p>
      </div>
      <div className="card">
        <h3>处理数据目录</h3>
        <p>{数据?.result?.processed_dir || '暂无'}</p>
      </div>
      {数据?.error ? <div className="error-box">{数据.error}</div> : null}
    </div>
  )
}
