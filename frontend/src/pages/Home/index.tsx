import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { 删除任务 as 删除任务接口, 获取结果, 获取任务列表 } from '../../api/task'
import type { 任务响应, 结果响应 } from '../../types/task'

type 结果缓存 = Record<string, { loading: boolean; data: 结果响应 | null; error: string }>
type AnyRecord = Record<string, any>

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
  if (status === 'failed' || status === 'stopped' || status === 'partial_success') return 'status-failed'
  if (['running', 'queued', 'retrying', 'stopping'].includes(status)) return 'status-running'
  return 'status-idle'
}

function isObject(value: unknown): value is AnyRecord {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function getNested(source: unknown, path: string[]) {
  let current: any = source
  for (const key of path) {
    if (!current || typeof current !== 'object') return undefined
    current = current[key]
  }
  return current
}

function pickFirst(source: unknown, paths: string[][]) {
  for (const path of paths) {
    const value = getNested(source, path)
    if (value !== undefined && value !== null && value !== '') return value
  }
  return undefined
}

function 格式化数值(value: unknown, digits = 4) {
  if (value === undefined || value === null || value === '') return '-'
  const numberValue = typeof value === 'number' ? value : Number(value)
  if (Number.isFinite(numberValue)) {
    if (Math.abs(numberValue) >= 1000) return String(Math.round(numberValue))
    return numberValue.toFixed(digits).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
  }
  return String(value)
}

function 格式化布尔(value: unknown) {
  if (value === true) return '开启'
  if (value === false) return '关闭'
  if (value === undefined || value === null || value === '') return '-'
  return String(value)
}

function 读取指标(task: 任务响应, result: 结果响应 | null, key: string) {
  return (
    pickFirst(result, [
      ['metrics_summary', key],
      ['metrics', key],
      ['experiment_info', 'metrics_summary', key],
      ['result', 'metrics_summary', key],
    ]) ?? pickFirst(task, [['metrics_summary', key]])
  )
}

function 读取实验信息(result: 结果响应 | null) {
  const info = pickFirst(result, [['experiment_info'], ['experimentInfo'], ['result', 'experiment_info'], ['result', 'experimentInfo']])
  return isObject(info) ? info : {}
}

function 读取配置快照(result: 结果响应 | null) {
  const snapshot = pickFirst(result, [['config_snapshot'], ['configSnapshot'], ['result', 'config_snapshot'], ['result', 'configSnapshot']])
  return isObject(snapshot) ? snapshot : {}
}

function TaskCard({
  task,
  resultState,
  deleting,
  onDelete,
}: {
  task: 任务响应
  resultState?: 结果缓存[string]
  deleting?: boolean
  onDelete: (task: 任务响应) => void
}) {
  const result = resultState?.data ?? null
  const experimentInfo = 读取实验信息(result)
  const configSnapshot = 读取配置快照(result)
  const trainProfile = isObject(experimentInfo.train_profile) ? experimentInfo.train_profile : {}

  const inputMode =
    experimentInfo.input_mode ??
    pickFirst(configSnapshot, [['pipeline', 'input_mode']]) ??
    '-'
  const augmentationEnabled =
    experimentInfo.augmentation_enabled ??
    pickFirst(configSnapshot, [['pipeline', 'run_augmentation']])
  const augmentationPreset =
    experimentInfo.augmentation_preset ??
    pickFirst(configSnapshot, [['augmentation', 'preset']]) ??
    '-'

  const psnr = 读取指标(task, result, 'psnr')
  const ssim = 读取指标(task, result, 'ssim')
  const lpips = 读取指标(task, result, 'lpips')
  const registrationRate = 读取指标(task, result, 'colmap_registration_rate')
  const registrationRateText =
    registrationRate === undefined || registrationRate === null || registrationRate === ''
      ? '-'
      : `${格式化数值(registrationRate, 2)}%`

  const outputDir =
    experimentInfo.output_dir ??
    pickFirst(result, [['result', 'output_dir'], ['result', 'report_dir']]) ??
    pickFirst(task, [['result', 'output_dir']]) ??
    '-'

  const 正在运行 = ['running', 'queued', 'retrying', 'stopping'].includes(task.status)
  const 删除按钮标题 = 正在运行 ? '任务正在执行，请先停止后再删除' : '删除任务记录和该任务的隔离输出文件'

  return (
    <div className="recent-task-card">
      <div className="recent-task-head">
        <div>
          <h4>{task.scene_name || '未命名场景'}</h4>
          <p className="mono-line">{task.task_id}</p>
        </div>
        <span className={`status-pill ${状态类名(task.status)}`}>{状态文本(task.status)}</span>
      </div>

      <div className="recent-task-meta-grid">
        <div>
          <span>输入模式</span>
          <strong>{inputMode === 'video' ? '视频抽帧' : inputMode === 'images' ? '图片目录' : String(inputMode)}</strong>
        </div>
        <div>
          <span>数据增强</span>
          <strong>
            {格式化布尔(augmentationEnabled)}
            {augmentationPreset && augmentationPreset !== '-' ? ` / ${augmentationPreset}` : ''}
          </strong>
        </div>
        <div>
          <span>训练模板</span>
          <strong>{trainProfile.active_profile || '-'}</strong>
        </div>
        <div>
          <span>迭代轮数</span>
          <strong>{格式化数值(trainProfile.iterations, 0)}</strong>
        </div>
      </div>

      <div className="recent-task-metrics">
        <div>
          <span>PSNR</span>
          <strong>{格式化数值(psnr)}</strong>
        </div>
        <div>
          <span>SSIM</span>
          <strong>{格式化数值(ssim)}</strong>
        </div>
        <div>
          <span>LPIPS</span>
          <strong>{格式化数值(lpips)}</strong>
        </div>
        <div>
          <span>注册率</span>
          <strong>{registrationRateText}</strong>
        </div>
      </div>

      <div className="recent-task-path">
        <span>输出目录</span>
        <strong title={String(outputDir)}>{String(outputDir)}</strong>
      </div>

      <div className="recent-task-footer">
        <span>创建：{格式化时间(task.created_at)}</span>
        <div className="inline-actions wrap-actions">
          <Link className="ghost-btn small-action-btn" to={`/tasks/${task.task_id}`}>
            运行页
          </Link>
          <Link className="primary-btn small-action-btn" to={`/results/${task.task_id}`}>
            结果页
          </Link>
          <button
            type="button"
            className="danger-btn small-action-btn"
            disabled={正在运行 || deleting}
            title={删除按钮标题}
            onClick={() => onDelete(task)}
          >
            {deleting ? '删除中…' : '删除'}
          </button>
        </div>
      </div>

      {resultState?.error ? <p className="recent-task-error">结果摘要暂不可用：{resultState.error}</p> : null}
      {resultState?.loading ? <p className="recent-task-loading">正在读取实验摘要…</p> : null}
    </div>
  )
}

export function HomePage() {
  const [任务列表, set任务列表] = useState<任务响应[]>([])
  const [结果列表, set结果列表] = useState<结果缓存>({})
  const [加载中, set加载中] = useState(true)
  const [错误, set错误] = useState('')
  const [提示, set提示] = useState('')
  const [删除中任务, set删除中任务] = useState<Record<string, boolean>>({})

  const 刷新任务列表 = async () => {
    try {
      set加载中(true)
      const items = await 获取任务列表()

      const sorted = [...items].sort((a, b) => {
        const aTime = new Date(a.created_at || 0).getTime()
        const bTime = new Date(b.created_at || 0).getTime()
        return bTime - aTime
      })

      const recent = sorted.slice(0, 8)
      set任务列表(recent)
      set错误('')
      set提示('')

      const initialCache: 结果缓存 = {}
      recent.forEach((item) => {
        initialCache[item.task_id] = { loading: true, data: null, error: '' }
      })
      set结果列表(initialCache)

      await Promise.allSettled(
        recent.map(async (item) => {
          try {
            const result = await 获取结果(item.task_id)
            set结果列表((prev) => ({
              ...prev,
              [item.task_id]: { loading: false, data: result, error: '' },
            }))
          } catch (error) {
            set结果列表((prev) => ({
              ...prev,
              [item.task_id]: {
                loading: false,
                data: null,
                error: error instanceof Error ? error.message : '获取失败',
              },
            }))
          }
        }),
      )
    } catch (error) {
      set错误(error instanceof Error ? error.message : '获取任务列表失败')
      set结果列表({})
    } finally {
      set加载中(false)
    }
  }

  const 删除任务记录 = async (task: 任务响应) => {
    if (['running', 'queued', 'retrying', 'stopping'].includes(task.status)) {
      set错误('任务正在执行，不能直接删除。请先停止任务，等待状态变为已停止或失败后再删除。')
      set提示('')
      return
    }

    const confirmed = window.confirm(
      `确认删除任务 ${task.task_id} 吗？\n\n系统会删除任务记录，并清理该任务独立目录下的 runtime、outputs、processed 和日志文件。原始图片目录不会被删除。`,
    )

    if (!confirmed) return

    set删除中任务((prev) => ({ ...prev, [task.task_id]: true }))
    set错误('')
    set提示('')

    try {
      const response = await 删除任务接口(task.task_id)

      if (!response.ok) {
        set错误(response.message || '删除任务失败')
        return
      }

      set任务列表((prev) => prev.filter((item) => item.task_id !== task.task_id))
      set结果列表((prev) => {
        const next = { ...prev }
        delete next[task.task_id]
        return next
      })
      set提示(response.message || '任务已删除')
    } catch (error) {
      set错误(error instanceof Error ? error.message : '删除任务失败')
    } finally {
      set删除中任务((prev) => {
        const next = { ...prev }
        delete next[task.task_id]
        return next
      })
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
    <div className="page home-page">
      <div className="page-header home-hero">
        <div>
          <h1>三维重建平台</h1>
          <p className="page-subtitle">
            本系统采用前后端分离架构，支持任务配置、流程调度、日志查看、数据增强实验对比与结果展示。
          </p>
        </div>
        <div className="inline-actions wrap-actions">
          <button type="button" className="ghost-btn" onClick={刷新任务列表} disabled={加载中}>
            {加载中 ? '刷新中…' : '刷新首页'}
          </button>
          <Link className="primary-btn" to="/tasks/create">
            创建任务
          </Link>
        </div>
      </div>

      {提示 ? <div className="success-box">{提示}</div> : null}
      {错误 ? <div className="error-box">{错误}</div> : null}

      <div className="card-grid home-feature-grid">
        <div className="card feature-card">
          <h3>前端界面</h3>
          <p className="section-tip">提供参数配置、任务创建、运行监控和结果展示功能。</p>
        </div>
        <div className="card feature-card">
          <h3>后端服务</h3>
          <p className="section-tip">负责任务创建、状态管理、配置生成和日志推送。</p>
        </div>
        <div className="card feature-card">
          <h3>重建引擎</h3>
          <p className="section-tip">集成 COLMAP、数据转换、模型训练、渲染、评测与查看器功能。</p>
        </div>
      </div>

      <div className="info-grid home-stat-grid">
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

      <div className="card recent-task-section">
        <div className="toolbar-row">
          <div>
            <h3>首页最近任务</h3>
            <p className="section-tip">
              展示最近创建的任务、关键实验参数和质量指标，可快速跳转到运行页或结果页。
            </p>
          </div>
        </div>

        {加载中 && !任务列表.length ? (
          <div className="empty-tip">正在加载最近任务…</div>
        ) : !任务列表.length ? (
          <div className="empty-tip">当前还没有任务记录，先创建一个任务试试。</div>
        ) : (
          <div className="recent-task-grid">
            {任务列表.map((item) => (
              <TaskCard
                key={item.task_id}
                task={item}
                resultState={结果列表[item.task_id]}
                deleting={!!删除中任务[item.task_id]}
                onDelete={删除任务记录}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
