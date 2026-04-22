import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { 获取结果 } from '../../api/task'
import type { 结果响应, 阶段记录 } from '../../types/task'

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

function 状态类名(status: string) {
  if (status === 'success') return 'status-success'
  if (status === 'failed' || status === 'stopped') return 'status-failed'
  return 'status-idle'
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

function 读取数字(value: unknown) {
  if (typeof value === 'number') return value
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function 指标显示(value: unknown, digits = 4) {
  const n = 读取数字(value)
  if (n === null) return '-'
  return n.toFixed(digits)
}

function 普通显示(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function 取字符串数组(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item)).filter(Boolean)
}

export function ResultPage() {
  const { taskId = '' } = useParams()
  const [结果, set结果] = useState<结果响应 | null>(null)
  const [加载中, set加载中] = useState(true)
  const [错误, set错误] = useState('')

  const 刷新结果 = async () => {
    if (!taskId) {
      set错误('任务编号缺失')
      set加载中(false)
      return
    }

    try {
      set加载中(true)
      const data = await 获取结果(taskId)
      set结果(data)
      set错误('')
    } catch (error) {
      set错误(error instanceof Error ? error.message : '获取结果失败')
    } finally {
      set加载中(false)
    }
  }

  useEffect(() => {
    刷新结果()
  }, [taskId])

  const metricsSummary = useMemo(() => {
    return (结果?.metrics_summary ?? {}) as Record<string, unknown>
  }, [结果])

  const resultFiles = useMemo(() => {
    return (结果?.result_files ?? {}) as Record<string, unknown>
  }, [结果])

  const resultBody = useMemo(() => {
    return (结果?.result ?? {}) as Record<string, unknown>
  }, [结果])

  const previewImages = useMemo(() => {
    const fromResult = 取字符串数组(resultBody.preview_images)
    if (fromResult.length) return fromResult
    return []
  }, [resultBody])

  const stageHistory = useMemo(() => {
    return ((结果?.stage_history ?? []) as 阶段记录[])
      .slice()
      .sort((a, b) => a.order - b.order)
  }, [结果])

  const 关键指标卡片 = [
    { label: 'PSNR', value: 指标显示(metricsSummary.psnr, 4) },
    { label: 'SSIM', value: 指标显示(metricsSummary.ssim, 4) },
    { label: 'LPIPS', value: 指标显示(metricsSummary.lpips, 4) },
    { label: 'MSE', value: 指标显示(metricsSummary.mse, 6) },
    { label: 'MAE', value: 指标显示(metricsSummary.mae, 6) },
    { label: 'Gaussian 数量', value: 普通显示(metricsSummary.gaussian_count) },
    { label: '最新迭代', value: 普通显示(metricsSummary.latest_iteration) },
    { label: '生成时间', value: 普通显示(metricsSummary.generated_at) },
  ]

  const 文件列表: Array<[string, unknown]> = [
    ['metrics.json', resultFiles.metrics_json],
    ['report.json', resultFiles.report_json],
    ['report.md', resultFiles.report_md],
    ['summary.csv', resultFiles.summary_csv],
    ['summary.txt', resultFiles.summary_txt],
  ]

  if (加载中 && !结果) {
    return (
      <div className="page">
        <h1>结果查看</h1>
        <div className="card">正在加载结果信息…</div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>结果查看</h1>
          <p className="page-subtitle">
            本页显示任务执行状态、评价指标、结果文件、阶段耗时和预览图像。
          </p>
        </div>
        <div className="inline-actions wrap-actions">
          <button className="ghost-btn" onClick={刷新结果}>
            刷新结果
          </button>
          <Link className="ghost-btn" to={`/tasks/${taskId}`}>
            返回任务页
          </Link>
        </div>
      </div>

      {错误 ? <div className="error-box">{错误}</div> : null}

      {结果 ? (
        <>
          <div className="info-grid">
            <div className="card info-card">
              <div className="meta-label">任务编号</div>
              <div className="meta-value">{结果.task_id}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">场景名称</div>
              <div className="meta-value">{结果.scene_name}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">任务状态</div>
              <div className={`status-pill ${状态类名(结果.status)}`}>
                {状态文本(结果.status)}
              </div>
            </div>
            <div className="card info-card">
              <div className="meta-label">当前阶段</div>
              <div className="meta-value">{结果.current_stage || '-'}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">重试次数</div>
              <div className="meta-value">{结果.retry_count}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">停止请求</div>
              <div className="meta-value">{结果.stop_requested ? '是' : '否'}</div>
            </div>
          </div>

          <div className="card">
            <h3>结果摘要</h3>
            <div className="details-grid">
              <div>
                <label>状态说明</label>
                <div className="meta-value">{结果.message || '-'}</div>
              </div>
              <div>
                <label>创建时间</label>
                <div className="meta-value">{格式化时间(结果.created_at)}</div>
              </div>
              <div>
                <label>开始时间</label>
                <div className="meta-value">{格式化时间(结果.started_at)}</div>
              </div>
              <div>
                <label>结束时间</label>
                <div className="meta-value">{格式化时间(结果.finished_at)}</div>
              </div>
              <div>
                <label>模型输出目录</label>
                <div className="meta-value">{普通显示(resultBody.output_dir)}</div>
              </div>
              <div>
                <label>日志目录</label>
                <div className="meta-value">{普通显示(resultBody.log_dir)}</div>
              </div>
              <div>
                <label>处理数据目录</label>
                <div className="meta-value">{普通显示(resultBody.processed_dir)}</div>
              </div>
              <div>
                <label>运行时配置目录</label>
                <div className="meta-value">{普通显示(resultBody.runtime_dir)}</div>
              </div>
            </div>
          </div>

          <div className="card">
            <h3>评价指标</h3>
            <div className="metric-grid">
              {关键指标卡片.map((item) => (
                <div key={item.label} className="metric-card">
                  <div className="meta-label">{item.label}</div>
                  <div className="meta-value">{item.value}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>结果文件</h3>
            <div className="file-grid">
              {文件列表.map(([name, value]) => (
                <div key={name} className="file-card">
                  <div className="meta-label">{name}</div>
                  <div className="file-value">{普通显示(value)}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>阶段耗时</h3>
            {stageHistory.length ? (
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
                    {stageHistory.map((item) => (
                      <tr key={`${item.stage_key}-${item.order}`}>
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

          <div className="card">
            <h3>预览图像</h3>
            {previewImages.length ? (
              <div className="preview-grid">
                {previewImages.map((src) => (
                  <div key={src} className="preview-card">
                    <img src={src} alt="预览图像" className="preview-image" />
                    <div className="preview-path">{src}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-tip">当前未找到可展示的预览图像。</div>
            )}
          </div>

          {结果.error ? (
            <div className="card">
              <h3>错误信息</h3>
              <div className="error-panel">{结果.error}</div>
            </div>
          ) : null}
        </>
      ) : (
        <div className="card">未找到结果信息。</div>
      )}
    </div>
  )
}