import { useEffect, useMemo, useState } from 'react'
import { 获取系统健康, 获取系统布局 } from '../../api/system'
import type { 布局检查响应, 系统设置 } from '../../types/settings'
import {
  默认系统设置,
  保存系统设置,
  读取系统设置,
  重置系统设置,
} from '../../utils/settings'

function 状态文本(flag: boolean) {
  return flag ? '正常' : '缺失'
}

export function SettingsPage() {
  const [表单, set表单] = useState<系统设置>(默认系统设置)
  const [保存提示, set保存提示] = useState('')
  const [错误, set错误] = useState('')
  const [健康状态, set健康状态] = useState<'idle' | 'ok' | 'failed'>('idle')
  const [布局信息, set布局信息] = useState<布局检查响应 | null>(null)
  const [检测中, set检测中] = useState(false)

  useEffect(() => {
    set表单(读取系统设置())
  }, [])

  const 环境摘要 = useMemo(
    () => [
      { label: '当前生效 API 地址', value: 表单.apiBaseUrl || '/api' },
      {
        label: '当前生效 WS 地址',
        value: 表单.wsBaseUrl || '自动按浏览器地址推断',
      },
      {
        label: '默认场景名',
        value: 表单.sceneDefaults.defaultSceneName || '未设置',
      },
      {
        label: '默认训练模板',
        value: 表单.trainDefaults.activeProfile || '未设置',
      },
    ],
    [表单],
  )

  const 执行检测 = async () => {
    try {
      set检测中(true)
      set错误('')
      const [health, layout] = await Promise.all([获取系统健康(), 获取系统布局()])
      set健康状态(health.status === 'ok' ? 'ok' : 'failed')
      set布局信息(layout)
    } catch (error) {
      set健康状态('failed')
      set错误(error instanceof Error ? error.message : '系统检测失败')
    } finally {
      set检测中(false)
    }
  }

  const 保存 = () => {
    try {
      保存系统设置(表单)
      set保存提示('系统设置已保存，新建任务页和接口请求会读取这些值。')
      set错误('')
      window.setTimeout(() => set保存提示(''), 2500)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '保存失败')
    }
  }

  const 恢复默认 = () => {
    重置系统设置()
    set表单(默认系统设置)
    set保存提示('已恢复默认设置。')
    set错误('')
    window.setTimeout(() => set保存提示(''), 2500)
  }

  return (
    <div className="page settings-page">
      <div className="page-header">
        <div>
          <h1>系统设置</h1>
          <p className="page-subtitle">
            用于配置系统默认参数。保存后，新建任务页会自动读取这些路径、工具位置和训练模板；接口请求也会优先使用这里的地址配置。
          </p>
        </div>
        <div className="inline-actions wrap-actions">
          <button className="ghost-btn" onClick={执行检测} disabled={检测中}>
            {检测中 ? '检测中…' : '检测后端'}
          </button>
          <button className="ghost-btn danger-btn" onClick={恢复默认}>
            恢复默认
          </button>
          <button className="primary-btn" onClick={保存}>
            保存设置
          </button>
        </div>
      </div>

      <div className="card-grid summary-grid">
        {环境摘要.map((item) => (
          <div className="card compact-card" key={item.label}>
            <div className="meta-label">{item.label}</div>
            <div className="meta-value">{item.value}</div>
          </div>
        ))}
      </div>

      {保存提示 ? <div className="success-box">{保存提示}</div> : null}
      {错误 ? <div className="error-box">{错误}</div> : null}

      <div className="settings-stack">
        <section className="card settings-section">
          <h3>连接设置</h3>
          <p className="section-tip">
            用于配置前后端通信地址，建议根据实际部署环境填写。
          </p>
          <div className="field-grid two-columns">
            <div>
              <label>API 基地址</label>
              <input
                value={表单.apiBaseUrl}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    apiBaseUrl: e.target.value,
                  })
                }
                placeholder="例如 /api 或 http://127.0.0.1:8000/api"
              />
            </div>
            <div>
              <label>WebSocket 基地址</label>
              <input
                value={表单.wsBaseUrl}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    wsBaseUrl: e.target.value,
                  })
                }
                placeholder="例如 ws://127.0.0.1:8000，留空时自动推断"
              />
            </div>
          </div>
          <div className="status-row">
            <span
              className={`status-pill ${健康状态 === 'ok'
                ? 'status-success'
                : 健康状态 === 'failed'
                  ? 'status-failed'
                  : 'status-idle'
                }`}
            >
              {健康状态 === 'idle'
                ? '尚未检测'
                : 健康状态 === 'ok'
                  ? '后端连接正常'
                  : '后端连接异常'}
            </span>
          </div>
        </section>

        <section className="card settings-section">
          <h3>默认目录</h3>
          <div className="field-grid two-columns">
            <div>
              <label>Gaussian Splatting 根目录</label>
              <input
                value={表单.systemPaths.gs_repo}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    systemPaths: { ...表单.systemPaths, gs_repo: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label>原始数据目录</label>
              <input
                value={表单.systemPaths.raw_data}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    systemPaths: { ...表单.systemPaths, raw_data: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label>处理数据目录</label>
              <input
                value={表单.systemPaths.processed_data}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    systemPaths: {
                      ...表单.systemPaths,
                      processed_data: e.target.value,
                    },
                  })
                }
              />
            </div>
            <div>
              <label>模型输出目录</label>
              <input
                value={表单.systemPaths.outputs}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    systemPaths: { ...表单.systemPaths, outputs: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label>日志目录</label>
              <input
                value={表单.systemPaths.logs}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    systemPaths: { ...表单.systemPaths, logs: e.target.value },
                  })
                }
              />
            </div>
            <div>
              <label>视频目录</label>
              <input
                value={表单.systemPaths.videos_data}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    systemPaths: {
                      ...表单.systemPaths,
                      videos_data: e.target.value,
                    },
                  })
                }
              />
            </div>
          </div>
        </section>

        <section className="settings-dual-grid">
          <div className="card settings-section">
            <h3>工具路径</h3>
            <div className="field-grid two-columns">
              <div>
                <label>COLMAP 可执行文件</label>
                <input
                  value={表单.tools.colmapExecutable}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      tools: {
                        ...表单.tools,
                        colmapExecutable: e.target.value,
                      },
                    })
                  }
                />
              </div>
              <div>
                <label>FFmpeg 可执行文件</label>
                <input
                  value={表单.tools.ffmpegExecutable}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      tools: {
                        ...表单.tools,
                        ffmpegExecutable: e.target.value,
                      },
                    })
                  }
                />
              </div>
              <div>
                <label>ImageMagick 可执行文件</label>
                <input
                  value={表单.tools.magickExecutable}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      tools: {
                        ...表单.tools,
                        magickExecutable: e.target.value,
                      },
                    })
                  }
                />
              </div>
              <div>
                <label>Viewer 根目录</label>
                <input
                  value={表单.tools.viewerRoot}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      tools: {
                        ...表单.tools,
                        viewerRoot: e.target.value,
                      },
                    })
                  }
                />
              </div>
            </div>
          </div>

          <div className="card settings-section">
            <h3>新建任务默认值</h3>
            <div className="field-grid two-columns">
              <div>
                <label>默认场景名</label>
                <input
                  value={表单.sceneDefaults.defaultSceneName}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      sceneDefaults: {
                        ...表单.sceneDefaults,
                        defaultSceneName: e.target.value,
                      },
                    })
                  }
                />
              </div>
              <div>
                <label>默认输入模式</label>
                <select
                  value={表单.sceneDefaults.inputMode}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      sceneDefaults: {
                        ...表单.sceneDefaults,
                        inputMode: e.target.value as 'images' | 'video',
                      },
                      pipelineDefaults: {
                        ...表单.pipelineDefaults,
                        input_mode: e.target.value as 'images' | 'video',
                      },
                    })
                  }
                >
                  <option value="images">图片</option>
                  <option value="video">视频</option>
                </select>
              </div>
            </div>

            <div className="switch-row">
              <label className="toggle-item">
                <input
                  type="checkbox"
                  checked={表单.sceneDefaults.autoFillPaths}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      sceneDefaults: {
                        ...表单.sceneDefaults,
                        autoFillPaths: e.target.checked,
                      },
                    })
                  }
                />
                <span>修改场景名时自动刷新路径</span>
              </label>
            </div>
          </div>
        </section>

        <section className="card settings-section">
          <h3>训练与流程默认值</h3>
          <p className="section-tip">
            用于设置训练参数和流程默认开关，页面采用分组布局便于查看与修改。
          </p>

          <div className="settings-subsection-grid">
            <div className="subsection-box">
              <h4>训练基础参数</h4>
              <div className="field-grid three-columns">
                <div>
                  <label>默认训练模板</label>
                  <input
                    value={表单.trainDefaults.activeProfile}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          activeProfile: e.target.value,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>训练轮数</label>
                  <input
                    type="number"
                    min={1}
                    value={表单.trainDefaults.iterations}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          iterations: Number(e.target.value) || 1,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>分辨率倍率</label>
                  <input
                    type="number"
                    min={1}
                    value={表单.trainDefaults.resolution}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          resolution: Number(e.target.value) || 1,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>数据设备</label>
                  <input
                    value={表单.trainDefaults.dataDevice}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          dataDevice: e.target.value,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>densify_grad_threshold</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={表单.trainDefaults.densifyGradThreshold}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          densifyGradThreshold: Number(e.target.value) || 0,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>densification_interval</label>
                  <input
                    type="number"
                    min={1}
                    value={表单.trainDefaults.densificationInterval}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          densificationInterval: Number(e.target.value) || 1,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>densify_until_iter</label>
                  <input
                    type="number"
                    min={0}
                    value={表单.trainDefaults.densifyUntilIter}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          densifyUntilIter: Number(e.target.value) || 0,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>save_iterations</label>
                  <input
                    value={表单.trainDefaults.saveIterations}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          saveIterations: e.target.value,
                        },
                      })
                    }
                    placeholder="例如 7000,30000"
                  />
                </div>
                <div>
                  <label>test_iterations</label>
                  <input
                    value={表单.trainDefaults.testIterations}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          testIterations: e.target.value,
                        },
                      })
                    }
                    placeholder="例如 -1"
                  />
                </div>
                <div className="full-width">
                  <label>checkpoint_iterations</label>
                  <input
                    value={表单.trainDefaults.checkpointIterations}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          checkpointIterations: e.target.value,
                        },
                      })
                    }
                    placeholder="例如 2000,15000,30000"
                  />
                </div>
                <div className="full-width">
                  <label>start_checkpoint</label>
                  <input
                    value={表单.trainDefaults.startCheckpoint}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          startCheckpoint: e.target.value,
                        },
                      })
                    }
                    placeholder="可留空"
                  />
                </div>
              </div>
            </div>

            <div className="subsection-box">
              <h4>流程与布尔开关</h4>
              <div className="toggle-grid compact-toggle-grid">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={表单.trainDefaults.eval}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          eval: e.target.checked,
                        },
                      })
                    }
                  />
                  <span>默认启用 eval</span>
                </label>
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={表单.trainDefaults.quiet}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          quiet: e.target.checked,
                        },
                      })
                    }
                  />
                  <span>默认 quiet</span>
                </label>
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={表单.trainDefaults.resumeFromLatest}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          resumeFromLatest: e.target.checked,
                        },
                      })
                    }
                  />
                  <span>默认从最新断点恢复</span>
                </label>
              </div>

              <div className="flag-grid compact-flag-grid">
                {(
                  [
                    ['run_preflight', '预检查'],
                    ['run_video_extract', '视频抽帧'],
                    ['run_augmentation', '数据增强'],
                    ['run_colmap', 'COLMAP'],
                    ['run_convert', '转换'],
                    ['run_train', '训练'],
                    ['run_render', '渲染'],
                    ['run_metrics', '评测'],
                    ['launch_viewer', '启动查看器'],
                  ] as Array<[keyof 系统设置['pipelineDefaults'], string]>
                ).map(([key, label]) => (
                  <label className="flag-card compact-flag-card" key={key}>
                    <input
                      type="checkbox"
                      checked={Boolean(表单.pipelineDefaults[key])}
                      onChange={(e) =>
                        set表单({
                          ...表单,
                          pipelineDefaults: {
                            ...表单.pipelineDefaults,
                            [key]: e.target.checked,
                          },
                        })
                      }
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="card settings-section">
        <h3>项目结构检测结果</h3>
        <p className="section-tip">
          本区域显示后端 /system/layout 接口返回的项目结构检查结果。
        </p>

        {布局信息 ? (
          <div className="layout-check-grid">
            <div className="compact-check-item">
              <span>项目根目录</span>
              <strong>{布局信息.project_root}</strong>
            </div>
            <div className="compact-check-item">
              <span>engine</span>
              <strong>{状态文本(布局信息.engine_exists)}</strong>
            </div>
            <div className="compact-check-item">
              <span>backend</span>
              <strong>{状态文本(布局信息.backend_exists)}</strong>
            </div>
            <div className="compact-check-item">
              <span>frontend</span>
              <strong>{状态文本(布局信息.frontend_exists)}</strong>
            </div>

            {Object.entries(布局信息.engine_dirs).map(([key, value]) => (
              <div className="compact-check-item" key={key}>
                <span>{key}</span>
                <strong>{状态文本(value)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-tip">
            点击“检测后端”后，这里显示项目目录和引擎结构检查结果。
          </div>
        )}
      </section>
    </div>
  )
}
