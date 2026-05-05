import { useEffect, useMemo, useState } from 'react'
import { 获取系统健康, 获取系统布局 } from '../../api/system'
import type { 布局检查响应, 系统设置 } from '../../types/settings'
import type { 数据增强预设 } from '../../types/task'
import {
  默认系统设置,
  保存系统设置,
  读取系统设置,
  重置系统设置,
  构建数据增强预设,
} from '../../utils/settings'

function 状态文本(flag: boolean) {
  return flag ? '正常' : '缺失'
}

function 数字值(value: string, fallback = 0) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

type 流程布尔字段 = Exclude<keyof 系统设置['pipelineDefaults'], 'input_mode'>

const 流程开关项: Array<[流程布尔字段, string, string]> = [
  ['run_preflight', '预检查', '检查图片、目录和训练输入是否完整'],
  ['run_video_extract', '视频抽帧', '视频模式下先抽帧到原始图片目录'],
  ['run_augmentation', '数据增强', '在 COLMAP 前进行安全图像增强'],
  ['run_colmap', 'COLMAP', '执行稀疏重建和相机位姿估计'],
  ['run_convert', '转换', '生成 3DGS 训练输入目录'],
  ['run_train', '训练', '调用官方 train.py'],
  ['run_render', '渲染', '训练后离线渲染预览'],
  ['run_metrics', '评测', '统计 PSNR / SSIM / COLMAP 质量等指标'],
  ['launch_viewer', '查看器', '训练完成后启动 Viewer'],
]

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
      { label: '当前 API', value: 表单.apiBaseUrl || '/api' },
      { label: '默认场景', value: 表单.sceneDefaults.defaultSceneName || '未设置' },
      { label: '默认流程', value: 表单.pipelineDefaults.run_augmentation ? '含数据增强' : '不含数据增强' },
      { label: '训练模板', value: `${表单.trainDefaults.activeProfile} / ${表单.trainDefaults.iterations} iter` },
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
      set保存提示('系统设置已保存，新建任务页会自动读取这些默认参数。')
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

  const 应用增强预设 = (preset: 数据增强预设) => {
    const next = 构建数据增强预设(preset)
    set表单({
      ...表单,
      augmentationDefaults: next,
      pipelineDefaults: {
        ...表单.pipelineDefaults,
        run_augmentation: next.enabled,
      },
    })
  }

  return (
    <div className="page settings-page">
      <div className="page-header">
        <div>
          <h1>系统设置</h1>
          <p className="page-subtitle">
            这里统一配置路径、工具、流程、训练和数据增强参数。保存后，新建任务会继承这些默认值；单个任务仍可在新建页再次微调。
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
          <p className="section-tip">用于配置前后端通信地址，建议根据实际部署环境填写。</p>
          <div className="field-grid two-columns">
            <div>
              <label>API 基地址</label>
              <input
                value={表单.apiBaseUrl}
                onChange={(e) => set表单({ ...表单, apiBaseUrl: e.target.value })}
                placeholder="例如 /api 或 http://127.0.0.1:8000/api"
              />
            </div>
            <div>
              <label>WebSocket 基地址</label>
              <input
                value={表单.wsBaseUrl}
                onChange={(e) => set表单({ ...表单, wsBaseUrl: e.target.value })}
                placeholder="例如 ws://127.0.0.1:8000，留空时自动推断"
              />
            </div>
          </div>
          <div className="status-row">
            <span
              className={`status-pill ${
                健康状态 === 'ok'
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
          <p className="section-tip">建议统一使用相对 engine 目录的路径，跨设备迁移时更稳定。</p>
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
                    systemPaths: { ...表单.systemPaths, processed_data: e.target.value },
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
                    systemPaths: { ...表单.systemPaths, videos_data: e.target.value },
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
                      tools: { ...表单.tools, colmapExecutable: e.target.value },
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
                      tools: { ...表单.tools, ffmpegExecutable: e.target.value },
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
                      tools: { ...表单.tools, magickExecutable: e.target.value },
                    })
                  }
                  placeholder="可留空"
                />
              </div>
              <div>
                <label>Viewer 根目录</label>
                <input
                  value={表单.tools.viewerRoot}
                  onChange={(e) =>
                    set表单({
                      ...表单,
                      tools: { ...表单.tools, viewerRoot: e.target.value },
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
                        run_video_extract:
                          e.target.value === 'video' ? true : 表单.pipelineDefaults.run_video_extract,
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
          <h3>流程默认开关</h3>
          <p className="section-tip">按 3DGS 正常处理顺序排列。数据增强位于 COLMAP 之前，只做图像级增强，不改变相机几何关系。</p>
          <div className="flag-grid compact-flag-grid">
            {流程开关项.map(([key, label, tip]) => (
              <label className="flag-card compact-flag-card flag-card-with-tip" key={key}>
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
                      augmentationDefaults:
                        key === 'run_augmentation'
                          ? { ...表单.augmentationDefaults, enabled: e.target.checked }
                          : 表单.augmentationDefaults,
                    })
                  }
                />
                <span>
                  <strong>{label}</strong>
                  <em>{tip}</em>
                </span>
              </label>
            ))}
          </div>
        </section>

        <section className="card settings-section">
          <h3>训练参数默认值</h3>
          <p className="section-tip">低显存机器建议 data_device=cpu、resolution=4 或 8；显存充足可切换 cuda。</p>
          <div className="settings-subsection-grid">
            <div className="subsection-box">
              <h4>基础训练</h4>
              <div className="field-grid three-columns">
                <div>
                  <label>默认训练模板</label>
                  <select
                    value={表单.trainDefaults.activeProfile}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: { ...表单.trainDefaults, activeProfile: e.target.value },
                      })
                    }
                  >
                    <option value="low_vram">low_vram</option>
                    <option value="normal">normal</option>
                    <option value="fast_preview">fast_preview</option>
                  </select>
                </div>
                <div>
                  <label>训练轮数 iterations</label>
                  <input
                    type="number"
                    min={1}
                    value={表单.trainDefaults.iterations}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          iterations: Math.max(1, 数字值(e.target.value, 1)),
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>分辨率倍率 resolution</label>
                  <input
                    type="number"
                    min={1}
                    value={表单.trainDefaults.resolution}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          resolution: Math.max(1, 数字值(e.target.value, 1)),
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>数据设备 data_device</label>
                  <select
                    value={表单.trainDefaults.dataDevice}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: { ...表单.trainDefaults, dataDevice: e.target.value },
                      })
                    }
                  >
                    <option value="cpu">cpu</option>
                    <option value="cuda">cuda</option>
                  </select>
                </div>
                <div>
                  <label>densify_grad_threshold</label>
                  <input
                    type="number"
                    min={0}
                    step="0.0001"
                    value={表单.trainDefaults.densifyGradThreshold}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: {
                          ...表单.trainDefaults,
                          densifyGradThreshold: Math.max(0, 数字值(e.target.value, 0)),
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
                          densificationInterval: Math.max(1, 数字值(e.target.value, 1)),
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
                          densifyUntilIter: Math.max(0, 数字值(e.target.value, 0)),
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
                        trainDefaults: { ...表单.trainDefaults, saveIterations: e.target.value },
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
                        trainDefaults: { ...表单.trainDefaults, testIterations: e.target.value },
                      })
                    }
                    placeholder="例如 -1"
                  />
                </div>
                <div>
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
                <div className="two-span">
                  <label>start_checkpoint</label>
                  <input
                    value={表单.trainDefaults.startCheckpoint}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: { ...表单.trainDefaults, startCheckpoint: e.target.value },
                      })
                    }
                    placeholder="可留空；填写后优先从该 checkpoint 恢复"
                  />
                </div>
              </div>
            </div>

            <div className="subsection-box">
              <h4>训练布尔项</h4>
              <div className="toggle-grid compact-toggle-grid">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={表单.trainDefaults.eval}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        trainDefaults: { ...表单.trainDefaults, eval: e.target.checked },
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
                        trainDefaults: { ...表单.trainDefaults, quiet: e.target.checked },
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
            </div>
          </div>
        </section>

        <section className="card settings-section">
          <h3>COLMAP / 视频参数</h3>
          <p className="section-tip">用于控制 COLMAP 重建和视频抽帧的默认行为。</p>
          <div className="field-grid three-columns">
            <div>
              <label>COLMAP 使用 GPU</label>
              <select
                value={表单.processDefaults.colmapUseGpu ? 'true' : 'false'}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    processDefaults: {
                      ...表单.processDefaults,
                      colmapUseGpu: e.target.value === 'true',
                    },
                  })
                }
              >
                <option value="true">启用</option>
                <option value="false">关闭</option>
              </select>
            </div>
            <div>
              <label>视频抽帧 FPS</label>
              <input
                type="number"
                min={1}
                step={1}
                value={表单.processDefaults.videoTargetFps}
                onChange={(e) =>
                  set表单({
                    ...表单,
                    processDefaults: {
                      ...表单.processDefaults,
                      videoTargetFps: Math.max(1, 数字值(e.target.value, 2)),
                    },
                  })
                }
              />
            </div>
          </div>
        </section>

        <section className="card settings-section augmentation-section">
          <div className="toolbar-row">
            <div>
              <h3>数据增强参数</h3>
              <p className="section-tip">
                这里的增强专门面向 3DGS / COLMAP：只做白平衡、CLAHE、Gamma、去噪、锐化、缩放，不做旋转、裁剪、翻转和仿射变换，避免破坏多视图几何一致性。
              </p>
            </div>
            <div className="inline-actions wrap-actions">
              <button type="button" className="ghost-btn" onClick={() => 应用增强预设('safe')}>安全增强</button>
              <button type="button" className="ghost-btn" onClick={() => 应用增强预设('low_light')}>低光照</button>
              <button type="button" className="ghost-btn" onClick={() => 应用增强预设('detail')}>细节增强</button>
              <button type="button" className="ghost-btn danger-btn" onClick={() => 应用增强预设('off')}>关闭增强</button>
            </div>
          </div>

          <div className="settings-subsection-grid">
            <div className="subsection-box">
              <h4>基础条件</h4>
              <div className="field-grid three-columns">
                <div>
                  <label>增强预设</label>
                  <select
                    value={表单.augmentationDefaults.preset}
                    onChange={(e) => 应用增强预设(e.target.value as 数据增强预设)}
                  >
                    <option value="safe">安全增强</option>
                    <option value="low_light">低光照增强</option>
                    <option value="detail">细节增强</option>
                    <option value="custom">自定义</option>
                    <option value="off">关闭</option>
                  </select>
                </div>
                <div>
                  <label>输出子目录</label>
                  <input
                    value={表单.augmentationDefaults.output_subdir}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          output_subdir: e.target.value,
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>JPEG 质量</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={表单.augmentationDefaults.jpeg_quality}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          jpeg_quality: Math.min(100, Math.max(1, 数字值(e.target.value, 95))),
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>最大长边</label>
                  <input
                    type="number"
                    min={0}
                    value={表单.augmentationDefaults.max_long_edge}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          max_long_edge: Math.max(0, 数字值(e.target.value, 0)),
                        },
                      })
                    }
                    placeholder="0 表示不限制"
                  />
                </div>
                <div>
                  <label>CLAHE clip_limit</label>
                  <input
                    type="number"
                    min={0.1}
                    step="0.1"
                    value={表单.augmentationDefaults.clahe_clip_limit}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          clahe_clip_limit: Math.max(0.1, 数字值(e.target.value, 2)),
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>CLAHE tile_grid_size</label>
                  <div className="inline-field-pair">
                    <input
                      type="number"
                      min={1}
                      value={表单.augmentationDefaults.clahe_tile_grid_size[0]}
                      onChange={(e) =>
                        set表单({
                          ...表单,
                          augmentationDefaults: {
                            ...表单.augmentationDefaults,
                            preset: 'custom',
                            clahe_tile_grid_size: [
                              Math.max(1, 数字值(e.target.value, 8)),
                              表单.augmentationDefaults.clahe_tile_grid_size[1],
                            ],
                          },
                        })
                      }
                    />
                    <input
                      type="number"
                      min={1}
                      value={表单.augmentationDefaults.clahe_tile_grid_size[1]}
                      onChange={(e) =>
                        set表单({
                          ...表单,
                          augmentationDefaults: {
                            ...表单.augmentationDefaults,
                            preset: 'custom',
                            clahe_tile_grid_size: [
                              表单.augmentationDefaults.clahe_tile_grid_size[0],
                              Math.max(1, 数字值(e.target.value, 8)),
                            ],
                          },
                        })
                      }
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="subsection-box">
              <h4>增强操作开关</h4>
              <div className="toggle-grid compact-toggle-grid">
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={表单.augmentationDefaults.enabled}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: e.target.checked ? 表单.augmentationDefaults.preset : 'off',
                          enabled: e.target.checked,
                        },
                        pipelineDefaults: {
                          ...表单.pipelineDefaults,
                          run_augmentation: e.target.checked,
                        },
                      })
                    }
                  />
                  <span>启用数据增强</span>
                </label>
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={表单.augmentationDefaults.overwrite}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          overwrite: e.target.checked,
                        },
                      })
                    }
                  />
                  <span>覆盖旧增强结果</span>
                </label>
                <label className="toggle-item">
                  <input
                    type="checkbox"
                    checked={表单.augmentationDefaults.keep_original_if_failed}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          keep_original_if_failed: e.target.checked,
                        },
                      })
                    }
                  />
                  <span>单张失败时复制原图</span>
                </label>
                {(
                  [
                    ['gray_world', '灰世界白平衡'],
                    ['clahe', 'CLAHE 局部对比度'],
                    ['auto_gamma', '自动 Gamma'],
                    ['denoise', '轻度去噪'],
                    ['sharpen', '轻度锐化'],
                  ] as Array<[keyof 系统设置['augmentationDefaults'], string]>
                ).map(([key, label]) => (
                  <label className="toggle-item" key={String(key)}>
                    <input
                      type="checkbox"
                      checked={Boolean(表单.augmentationDefaults[key])}
                      onChange={(e) =>
                        set表单({
                          ...表单,
                          augmentationDefaults: {
                            ...表单.augmentationDefaults,
                            preset: 'custom',
                            [key]: e.target.checked,
                          },
                        })
                      }
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>

              <div className="field-grid three-columns">
                <div>
                  <label>Gamma 目标亮度</label>
                  <input
                    type="number"
                    min={0.1}
                    max={0.9}
                    step="0.01"
                    value={表单.augmentationDefaults.gamma_target_mean}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          gamma_target_mean: Math.min(0.9, Math.max(0.1, 数字值(e.target.value, 0.48))),
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>去噪强度 h</label>
                  <input
                    type="number"
                    min={0}
                    step="0.1"
                    value={表单.augmentationDefaults.denoise_h}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          denoise_h: Math.max(0, 数字值(e.target.value, 3)),
                        },
                      })
                    }
                  />
                </div>
                <div>
                  <label>锐化强度</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step="0.05"
                    value={表单.augmentationDefaults.sharpen_amount}
                    onChange={(e) =>
                      set表单({
                        ...表单,
                        augmentationDefaults: {
                          ...表单.augmentationDefaults,
                          preset: 'custom',
                          sharpen_amount: Math.min(1, Math.max(0, 数字值(e.target.value, 0.2))),
                        },
                      })
                    }
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <section className="card settings-section">
        <h3>项目结构检测结果</h3>
        <p className="section-tip">本区域显示后端 /system/layout 接口返回的项目结构检查结果。</p>

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
          <div className="empty-tip">点击“检测后端”后，这里显示项目目录和引擎结构检查结果。</div>
        )}
      </section>
    </div>
  )
}
