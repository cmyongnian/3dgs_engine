import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { 获取结果 } from '../../api/task'

type AnyRecord = Record<string, any>

function 格式化时间(value: string | null | undefined) {
  if (!value) return '-'

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString()
}

function 状态文本(status: string | undefined) {
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
    unknown: '未知',
  }

  return status ? map[status] ?? status : '-'
}

function 状态类名(status: string | undefined) {
  if (status === 'success') return 'status-success'
  if (status === 'failed' || status === 'stopped') return 'status-failed'
  if (status === 'partial_success') return 'status-warning'
  if (status === 'running' || status === 'queued' || status === 'retrying' || status === 'stopping') {
    return 'status-running'
  }

  return 'status-idle'
}

function 质量类名(level: string | undefined) {
  if (level === '良好') return 'status-success'
  if (level === '一般') return 'status-warning'
  if (level === '较差' || level === '失败') return 'status-failed'
  return 'status-idle'
}

function 格式化值(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'

  if (typeof value === 'number') {
    if (Number.isInteger(value)) return String(value)
    return value.toFixed(4)
  }

  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }

  if (Array.isArray(value)) {
    return value.length ? value.join(', ') : '-'
  }

  if (typeof value === 'object') {
    return JSON.stringify(value, null, 2)
  }

  return String(value)
}

function 文件名(label: string) {
  const map: Record<string, string> = {
    metrics_json: '指标文件 metrics.json',
    report_json: '报告文件 report.json',
    report_md: 'Markdown 报告 report.md',
    summary_csv: '汇总表 summary.csv',
    summary_txt: '文本摘要 summary.txt',
    colmap_quality_json: 'COLMAP 质量分析 JSON',
    colmap_quality_txt: 'COLMAP 质量分析 TXT',
  }

  return map[label] ?? label
}

function 路径值(value: unknown) {
  if (typeof value !== 'string') return ''
  return value
}

function 是否有效值(value: unknown) {
  return value !== null && value !== undefined && value !== ''
}

async function 复制文本(text: string) {
  await navigator.clipboard.writeText(text)
}

export function ResultPage() {
  const { taskId = '' } = useParams()
  const navigate = useNavigate()

  const [结果, set结果] = useState<AnyRecord | null>(null)
  const [加载中, set加载中] = useState(true)
  const [错误, set错误] = useState('')
  const [提示, set提示] = useState('')

  const metricsSummary = useMemo<AnyRecord>(() => {
    return 结果?.metrics_summary ?? {}
  }, [结果])

  const result = useMemo<AnyRecord>(() => {
    return 结果?.result ?? {}
  }, [结果])

  const resultFiles = useMemo<AnyRecord>(() => {
    return 结果?.result_files ?? {}
  }, [结果])

  const colmapQuality = useMemo<AnyRecord>(() => {
    return result?.colmap_quality ?? {}
  }, [result])

  const 核心指标列表 = useMemo(() => {
    return [
      ['PSNR', metricsSummary.psnr],
      ['SSIM', metricsSummary.ssim],
      ['LPIPS', metricsSummary.lpips],
      ['MSE', metricsSummary.mse],
      ['MAE', metricsSummary.mae],
      ['Gaussian 数量', metricsSummary.gaussian_count],
      ['最新迭代次数', metricsSummary.latest_iteration],
      ['生成时间', metricsSummary.generated_at],
    ].filter(([, value]) => 是否有效值(value))
  }, [metricsSummary])

  const colmap指标列表 = useMemo(() => {
    const data = colmapQuality

    return [
      ['质量等级', data.quality_level],
      ['是否建议继续', data.can_continue],
      ['输入图像数量', data.input_image_count],
      ['注册图像数量', data.registered_image_count],
      [
        '图像注册率',
        是否有效值(data.registration_rate_percent)
          ? `${data.registration_rate_percent}%`
          : undefined,
      ],
      ['相机数量', data.camera_count],
      ['稀疏点数量', data.point3d_count],
      ['平均观测数', data.mean_track_length],
      ['平均重投影误差', data.mean_reprojection_error],
      ['模型格式', data.model_format],
      ['sparse 模型路径', data.sparse_model_path],
      ['生成时间', data.generated_at],
    ].filter(([, value]) => 是否有效值(value))
  }, [colmapQuality])

  const 文件列表 = useMemo(() => {
    return Object.entries(resultFiles).filter(([, value]) => Boolean(value))
  }, [resultFiles])

  const 路径列表 = useMemo(() => {
    return [
      ['输出目录', result.output_dir],
      ['报告目录', result.report_dir],
      ['日志目录', result.log_dir],
      ['处理后数据目录', result.processed_dir],
      ['运行时目录', result.runtime_dir],
      ['源数据目录', result.source_dir],
      ['原始图像目录', result.raw_image_dir],
    ].filter(([, value]) => Boolean(value))
  }, [result])

  const 预览图片 = useMemo(() => {
    const images = result.preview_images
    return Array.isArray(images) ? images.filter((item): item is string => typeof item === 'string') : []
  }, [result])

  async function 加载结果() {
    if (!taskId) {
      set错误('任务编号缺失')
      set加载中(false)
      return
    }

    try {
      set加载中(true)
      const data = await 获取结果(taskId)
      set结果(data as AnyRecord)
      set错误('')
    } catch (error) {
      set错误(error instanceof Error ? error.message : '获取结果失败')
    } finally {
      set加载中(false)
    }
  }

  async function 复制路径(path: string) {
    if (!path) return

    try {
      await 复制文本(path)
      set提示('路径已复制到剪贴板')

      window.setTimeout(() => {
        set提示('')
      }, 2500)
    } catch {
      set错误('复制失败：浏览器不允许访问剪贴板')
    }
  }

  useEffect(() => {
    加载结果()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId])

  if (加载中) {
    return (
      <div className="page">
        <h1>结果查看</h1>
        <div className="card">正在加载结果信息…</div>
      </div>
    )
  }

  if (!结果) {
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1>结果查看</h1>
            <p className="page-subtitle">未找到该任务的结果信息。</p>
          </div>

          <div className="inline-actions wrap-actions">
            <button className="ghost-btn" onClick={() => navigate(-1)}>
              返回
            </button>

            <Link className="primary-btn" to="/">
              回到首页
            </Link>
          </div>
        </div>

        {错误 ? <div className="error-box">{错误}</div> : null}
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>结果查看</h1>
          <p className="page-subtitle">
            查看三维重建任务的结果文件、评价指标、COLMAP 重建质量和输出路径。
          </p>
        </div>

        <div className="inline-actions wrap-actions">
          <button className="ghost-btn" onClick={加载结果}>
            刷新结果
          </button>

          <Link className="ghost-btn" to={`/tasks/${taskId}`}>
            返回任务
          </Link>

          <Link className="primary-btn" to="/">
            回到首页
          </Link>
        </div>
      </div>

      {提示 ? <div className="success-box">{提示}</div> : null}
      {错误 ? <div className="error-box">{错误}</div> : null}

      <div className="info-grid">
        <div className="card info-card">
          <div className="meta-label">任务编号</div>
          <div className="meta-value">{结果.task_id || taskId}</div>
        </div>

        <div className="card info-card">
          <div className="meta-label">场景名称</div>
          <div className="meta-value">{结果.scene_name || '-'}</div>
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
          <div className="meta-value">{结果.retry_count ?? 0}</div>
        </div>

        <div className="card info-card">
          <div className="meta-label">下一步停止请求</div>
          <div className="meta-value">{结果.stop_requested ? '是' : '否'}</div>
        </div>

        <div className="card info-card">
          <div className="meta-label">立即停止请求</div>
          <div className="meta-value">{结果.force_stop_requested ? '是' : '否'}</div>
        </div>
      </div>

      <div className="card">
        <h3>核心评价指标</h3>

        {核心指标列表.length ? (
          <div className="metric-grid">
            {核心指标列表.map(([label, value]) => (
              <div className="metric-card" key={String(label)}>
                <div className="meta-label">{label}</div>
                <div className="meta-value">{格式化值(value)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-tip">
            当前还没有 PSNR、SSIM、LPIPS 等评价指标。若任务未执行评测阶段，这是正常现象。
          </div>
        )}
      </div>

      <div className="card colmap-quality-card">
        <div className="toolbar-row">
          <div>
            <h3>COLMAP 重建质量分析</h3>
            <p className="section-tip">
              用于评估相机位姿估计和稀疏点云质量，帮助判断是否适合进入 3DGS 训练。
            </p>
          </div>

          {colmapQuality.quality_level ? (
            <div className={`status-pill ${质量类名(colmapQuality.quality_level)}`}>
              {colmapQuality.quality_level}
            </div>
          ) : null}
        </div>

        {colmap指标列表.length ? (
          <>
            <div className="metric-grid">
              {colmap指标列表.map(([label, value]) => (
                <div className="metric-card" key={String(label)}>
                  <div className="meta-label">{label}</div>
                  <div className="meta-value">{格式化值(value)}</div>
                </div>
              ))}
            </div>

            {Array.isArray(colmapQuality.suggestions) && colmapQuality.suggestions.length ? (
              <div className="quality-suggestion-box">
                <h4>优化建议</h4>

                <ul>
                  {colmapQuality.suggestions.map((item: string, index: number) => (
                    <li key={`${index}-${item}`}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : (
          <div className="empty-tip">
            暂未发现 COLMAP 质量分析结果。请确认任务是否执行到“COLMAP 质量分析”阶段，
            或检查是否生成 colmap_quality.json。
          </div>
        )}
      </div>

      <div className="card">
        <h3>结果文件</h3>

        {文件列表.length ? (
          <div className="file-grid">
            {文件列表.map(([key, value]) => {
              const path = 路径值(value)

              return (
                <div className="file-card" key={key}>
                  <div className="file-card-head">
                    <div className="meta-label">{文件名(key)}</div>

                    {path ? (
                      <button className="ghost-btn small-copy-btn" onClick={() => 复制路径(path)}>
                        复制
                      </button>
                    ) : null}
                  </div>

                  <div className="file-value">{格式化值(value)}</div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="empty-tip">
            暂未发现结果文件。若任务尚未执行到渲染、评测或报告阶段，这是正常现象。
          </div>
        )}
      </div>

      <div className="card">
        <h3>输出路径</h3>

        {路径列表.length ? (
          <div className="file-grid">
            {路径列表.map(([label, value]) => {
              const path = 路径值(value)

              return (
                <div className="file-card" key={String(label)}>
                  <div className="file-card-head">
                    <div className="meta-label">{label}</div>

                    {path ? (
                      <button className="ghost-btn small-copy-btn" onClick={() => 复制路径(path)}>
                        复制
                      </button>
                    ) : null}
                  </div>

                  <div className="file-value">{格式化值(value)}</div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="empty-tip">当前没有可显示的输出路径。</div>
        )}
      </div>

      <div className="card">
        <h3>预览图片</h3>

        {预览图片.length ? (
          <div className="preview-grid">
            {预览图片.map((path) => (
              <div className="preview-card" key={path}>
                <img
                  className="preview-image"
                  src={path}
                  alt="渲染预览"
                  onError={(event) => {
                    event.currentTarget.style.display = 'none'
                  }}
                />

                <div className="preview-path">{path}</div>

                <button className="ghost-btn small-copy-btn" onClick={() => 复制路径(path)}>
                  复制路径
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-tip">
            暂无预览图片。若后端返回的是本地磁盘绝对路径，浏览器可能无法直接显示图片，但路径仍可复制查看。
          </div>
        )}
      </div>

      <div className="card">
        <h3>时间信息</h3>

        <div className="details-grid">
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

          <div className="details-full">
            <label>状态说明</label>
            <div className="meta-value">{结果.message || '-'}</div>
          </div>

          {结果.error ? (
            <div className="details-full">
              <label>错误信息</label>
              <div className="error-panel">{结果.error}</div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}