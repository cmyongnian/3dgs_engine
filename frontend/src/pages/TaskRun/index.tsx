import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { 日志地址 } from '../../api/client'
import { 获取任务, 获取任务日志, 停止任务, 立即停止任务, 重试任务, 删除任务 } from '../../api/task'
import type { 阶段记录, 任务响应 } from '../../types/task'

type 日志连接状态 = 'connecting' | 'connected' | 'closed' | 'error'
type 操作类型 = 'stop' | 'force_stop' | 'retry' | 'delete' | 'refresh' | null

const 结束状态 = new Set(['success', 'failed', 'stopped', 'partial_success'])
const 可重试状态 = new Set(['failed', 'stopped', 'partial_success'])
const 可查看结果状态 = new Set(['success', 'partial_success', 'failed', 'stopped'])
const 可删除状态 = new Set(['success', 'failed', 'stopped', 'partial_success'])
const 不可删除状态 = new Set(['running', 'queued', 'stopping', 'retrying'])

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

function 日志连接状态文本(status: 日志连接状态) {
  const map: Record<日志连接状态, string> = {
    connecting: '日志连接中',
    connected: '日志已连接',
    closed: '日志已关闭',
    error: '日志连接异常',
  }
  return map[status]
}

function 状态类名(status: string) {
  if (status === 'success') return 'status-success'
  if (status === 'failed' || status === 'stopped') return 'status-failed'
  if (status === 'partial_success') return 'status-warning'
  if (status === 'running' || status === 'queued' || status === 'retrying' || status === 'stopping') return 'status-running'
  return 'status-idle'
}

function 日志连接状态类名(status: 日志连接状态) {
  if (status === 'connected') return 'ws-status ws-connected'
  if (status === 'error') return 'ws-status ws-error'
  if (status === 'closed') return 'ws-status ws-closed'
  return 'ws-status ws-connecting'
}

function 阶段卡片类名(status: string) {
  if (status === 'success') return 'phase-card phase-card-success'
  if (status === 'failed' || status === 'stopped') return 'phase-card phase-card-failed'
  if (status === 'running') return 'phase-card phase-card-running'
  return 'phase-card'
}

function 日志级别类名(line: string) {
  const lower = line.toLowerCase()
  if (lower.includes('traceback') || lower.includes('error') || lower.includes('failed') || lower.includes('失败')) {
    return 'log-row log-row-error'
  }
  if (lower.includes('warning') || lower.includes('warn') || lower.includes('警告')) {
    return 'log-row log-row-warning'
  }
  if (lower.includes('success') || lower.includes('done') || lower.includes('完成')) {
    return 'log-row log-row-success'
  }
  return 'log-row'
}

function 归一化日志文本(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter(Boolean)
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
  const [日志状态, set日志状态] = useState<日志连接状态>('connecting')
  const [当前操作, set当前操作] = useState<操作类型>(null)

  const 日志容器引用 = useRef<HTMLDivElement | null>(null)
  const ws引用 = useRef<WebSocket | null>(null)
  const 重连计时器引用 = useRef<number | null>(null)
  const 已结束引用 = useRef(false)
  const 日志签名集合引用 = useRef<Set<string>>(new Set())

  const 已结束 = useMemo(() => {
    if (!任务) return false
    return 结束状态.has(任务.status)
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

  const 运行中阶段数 = useMemo(() => {
    return 阶段列表.filter((item) => item.status === 'running').length
  }, [阶段列表])

  const 进度百分比 = useMemo(() => {
    if (!任务) return 0
    if (任务.status === 'success') return 100
    const base = 成功阶段数 + 运行中阶段数 * 0.5
    return Math.min(99, Math.max(0, Math.round((base / Math.max(阶段列表.length, 1)) * 100)))
  }, [任务, 成功阶段数, 运行中阶段数, 阶段列表.length])

  const 最近失败阶段 = useMemo(() => {
    const reversed = [...(任务?.stage_history ?? [])].reverse()
    return reversed.find((item) => item.status === 'failed') ?? null
  }, [任务])

  const 最近错误日志 = useMemo(() => {
    return [...日志列表].reverse().find((line) => 日志级别类名(line).includes('error')) ?? ''
  }, [日志列表])

  const 追加日志 = (text: string, options?: { dedupe?: boolean }) => {
    const lines = 归一化日志文本(text)
    if (!lines.length) return

    set日志列表((prev) => {
      const next = [...prev]

      for (const line of lines) {
        const signature = `${next.length}:${line}`
        const dedupeSignature = line

        if (options?.dedupe && 日志签名集合引用.current.has(dedupeSignature)) {
          continue
        }

        日志签名集合引用.current.add(options?.dedupe ? dedupeSignature : signature)
        next.push(line)
      }

      if (next.length > 3000) {
        const sliced = next.slice(next.length - 3000)
        日志签名集合引用.current = new Set(sliced)
        return sliced
      }

      return next
    })
  }

  const 清理重连计时器 = () => {
    if (重连计时器引用.current) {
      window.clearTimeout(重连计时器引用.current)
      重连计时器引用.current = null
    }
  }

 const 关闭日志连接 = () => {
   清理重连计时器()

   const ws = ws引用.current
   if (!ws) return

   ws引用.current = null

   ws.onmessage = null
   ws.onerror = null
   ws.onclose = null

   if (ws.readyState === WebSocket.CONNECTING) {
    // 避免浏览器提示：WebSocket is closed before the connection is established.
    // 等连接建立后再关闭，不影响页面功能。
     ws.onopen = () => {
       try {
         ws.close()
       } catch {
        // 忽略关闭过程中的浏览器差异
       }
     }
     return
   }

   ws.onopen = null

   if (ws.readyState === WebSocket.OPEN) {
     try {
       ws.close()
     } catch {
      // 忽略关闭过程中的浏览器差异
     }
   }
 }
  const 刷新任务 = async (静默 = false) => {
    if (!taskId) return

    try {
      if (!静默) {
        set加载中(true)
        set当前操作('refresh')
      }

      const data = await 获取任务(taskId)
      set任务(data)
      已结束引用.current = 结束状态.has(data.status)
      set错误('')
    } catch (error) {
      const message = error instanceof Error ? error.message : '获取任务失败'

      if (!静默) {
        set错误(message)
      } else {
        console.warn('静默刷新失败:', message)
      }
    } finally {
      if (!静默) {
        set加载中(false)
        set当前操作(null)
      }
    }
  }

  const 加载历史日志 = async () => {
    if (!taskId) return

    try {
      const data = await 获取任务日志(taskId)
      const lines = data.lines ?? []
      if (!lines.length) return

      日志签名集合引用.current = new Set(lines)
      set日志列表(lines.slice(-3000))
    } catch (error) {
      // 兼容尚未升级后端的情况：历史日志失败不影响实时日志。
      console.warn('历史日志加载失败:', error instanceof Error ? error.message : error)
    }
  }

  const 连接日志 = () => {
    if (!taskId) return

    关闭日志连接()
    set日志状态('connecting')

    const ws = new WebSocket(日志地址(taskId))
    ws引用.current = ws

    ws.onopen = () => {
      set日志状态('connected')
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('ping')
      }
    }

    ws.onmessage = (event) => {
      追加日志(String(event.data ?? ''))
    }

    ws.onerror = () => {
      set日志状态('error')
    }

    ws.onclose = () => {
      set日志状态('closed')

      if (已结束引用.current) {
        return
      }

      清理重连计时器()
      重连计时器引用.current = window.setTimeout(() => {
        连接日志()
      }, 2000)
    }
  }

  useEffect(() => {
    if (!taskId) {
      set错误('任务编号缺失')
      set加载中(false)
      return
    }

    刷新任务()
    加载历史日志()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId])

  useEffect(() => {
    已结束引用.current = 已结束
  }, [已结束])

 useEffect(() => {
   if (!taskId || 已结束) {
     关闭日志连接()
     return
   }

   连接日志()

   const pingTimer = window.setInterval(() => {
     const ws = ws引用.current
     if (ws && ws.readyState === WebSocket.OPEN) {
       ws.send('ping')
     }
   }, 15000)

   return () => {
     window.clearInterval(pingTimer)
     关闭日志连接()
   }
  // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [taskId, 已结束])
 
  useEffect(() => {
    if (!taskId || 已结束) return

    const timer = window.setInterval(() => {
      刷新任务(true)
    }, 2000)

    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, 已结束])

  useEffect(() => {
    if (!自动滚动) return
    const el = 日志容器引用.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [日志列表, 自动滚动])

  useEffect(() => {
    if (!提示) return
    const timer = window.setTimeout(() => set提示(''), 3000)
    return () => window.clearTimeout(timer)
  }, [提示])

  const 执行停止 = async () => {
    if (!taskId || 当前操作) return

    try {
      set当前操作('stop')
      const data = await 停止任务(taskId)
      set提示(data.message)
      await 刷新任务(true)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '停止任务失败')
    } finally {
      set当前操作(null)
    }
  }

  const 执行立即停止 = async () => {
    if (!taskId || 当前操作) return

    const confirmed = window.confirm('立即停止会尝试终止当前正在运行的外部子进程。确定要立即停止吗？')
    if (!confirmed) return

    try {
      set当前操作('force_stop')
      const data = await 立即停止任务(taskId)
      set提示(data.message)
      await 刷新任务(true)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '立即停止任务失败')
    } finally {
      set当前操作(null)
    }
  }

  const 执行重试 = async () => {
    if (!taskId || 当前操作) return

    try {
      set当前操作('retry')
      const data = await 重试任务(taskId)

      set提示(data.message)
      set错误('')
      set日志列表([])
      日志签名集合引用.current = new Set()
      已结束引用.current = false

      set任务((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          status: String(data.status) as typeof prev.status,
          current_stage: '等待重试',
          message: data.message,
          error: null,
          stage_history: [],
        }
      })

      连接日志()

      window.setTimeout(() => {
        刷新任务(true).catch(() => {
          // 重试刚触发时，后端若短暂不可读，不立刻报错。
        })
      }, 800)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '重试任务失败')
    } finally {
      set当前操作(null)
    }
  }

  const 执行删除 = async () => {
    if (!taskId || 当前操作) return

    if (任务 && 不可删除状态.has(任务.status)) {
      set错误('任务正在执行，不能删除。请先停止任务或等待任务结束。')
      return
    }

    const confirmed = window.confirm('确定要删除该任务记录吗？该操作不会自动删除输出文件。')
    if (!confirmed) return

    try {
      set当前操作('delete')
      const data = await 删除任务(taskId)

      if (!data.ok) {
        set错误(data.message)
        return
      }

      set提示(data.message)
      window.setTimeout(() => {
        navigate('/')
      }, 800)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '删除任务失败')
    } finally {
      set当前操作(null)
    }
  }

  const 复制日志 = async () => {
    try {
      await navigator.clipboard.writeText(日志列表.join('\n'))
      set提示('日志已复制到剪贴板')
    } catch {
      set错误('复制失败：浏览器不允许访问剪贴板')
    }
  }

  const 清空日志窗口 = () => {
    set日志列表([])
    日志签名集合引用.current = new Set()
    set提示('前端日志窗口已清空，不影响后端任务日志')
  }

  const 重新连接日志 = () => {
    已结束引用.current = false
    连接日志()
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
          <button className="ghost-btn" onClick={() => 刷新任务()} disabled={当前操作 !== null}>
            {当前操作 === 'refresh' ? '刷新中…' : '刷新状态'}
          </button>

          {!已结束 ? (
            <>
              <button className="ghost-btn danger-btn" onClick={执行停止} disabled={当前操作 !== null}>
                {当前操作 === 'stop' ? '提交中…' : '下一步停止'}
              </button>
              <button className="ghost-btn danger-btn" onClick={执行立即停止} disabled={当前操作 !== null}>
                {当前操作 === 'force_stop' ? '立即停止中…' : '立即停止'}
              </button>
            </>
          ) : null}

          {任务 && 可重试状态.has(任务.status) ? (
            <button className="ghost-btn" onClick={执行重试} disabled={当前操作 !== null}>
              {当前操作 === 'retry' ? '重试中…' : '重试任务'}
            </button>
          ) : null}

          {任务 && 可查看结果状态.has(任务.status) ? (
            <Link className="primary-btn" to={`/results/${taskId}`}>
              查看结果
            </Link>
          ) : null}

          {任务 && 可删除状态.has(任务.status) ? (
            <button className="ghost-btn danger-btn" onClick={执行删除} disabled={当前操作 !== null}>
              {当前操作 === 'delete' ? '删除中…' : '删除记录'}
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
              <div className="meta-label">下一步停止请求</div>
              <div className="meta-value">{任务.stop_requested ? '是' : '否'}</div>
            </div>
            <div className="card info-card">
              <div className="meta-label">立即停止请求</div>
              <div className="meta-value">{任务.force_stop_requested ? '是' : '否'}</div>
            </div>
          </div>

          <div className="card">
            <div className="toolbar-row">
              <div>
                <h3>执行进度</h3>
                <p className="section-tip">
                  当前进度根据阶段成功数和运行中阶段估算，用于反映整体执行状态。
                </p>
              </div>
              <div className="progress-text">{进度百分比}%</div>
            </div>

            <div className="progress-track">
              <div className="progress-bar" style={{ width: `${进度百分比}%` }} />
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
                {最近错误日志 ? (
                  <div className="details-full">
                    <label>最近错误日志</label>
                    <div className="error-panel">{最近错误日志}</div>
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="card log-card">
            <div className="log-toolbar">
              <div>
                <h3 className="section-title-tight">实时日志</h3>
                <div className="section-tip">
                  日志通过 WebSocket 推送；页面打开时会优先加载后端已缓存的历史日志。
                  <span className={日志连接状态类名(日志状态)}>{日志连接状态文本(日志状态)}</span>
                </div>
              </div>

              <div className="log-actions">
                <label className="inline-check">
                  <input
                    type="checkbox"
                    checked={自动滚动}
                    onChange={(e) => set自动滚动(e.target.checked)}
                  />
                  <span>自动滚动</span>
                </label>

                <button className="ghost-btn" type="button" onClick={重新连接日志}>
                  重连日志
                </button>

                <button
                  className="ghost-btn"
                  type="button"
                  onClick={复制日志}
                  disabled={日志列表.length === 0}
                >
                  复制日志
                </button>

                <button
                  className="ghost-btn danger-btn"
                  type="button"
                  onClick={清空日志窗口}
                  disabled={日志列表.length === 0}
                >
                  清空窗口
                </button>
              </div>
            </div>

            <div className="log-stream" ref={日志容器引用}>
              {日志列表.length ? (
                日志列表.map((line, index) => (
                  <div className={日志级别类名(line)} key={`${index}-${line.slice(0, 32)}`}>
                    <span className="log-index">{String(index + 1).padStart(4, '0')}</span>
                    <span className="log-text">{line}</span>
                  </div>
                ))
              ) : (
                <div className="log-empty">当前尚未收到日志输出。</div>
              )}
            </div>
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
