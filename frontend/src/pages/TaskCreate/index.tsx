import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { 创建任务, 启动任务 } from '../../api/task'
import type { 创建任务请求 } from '../../types/task'
import {
  根据场景名更新路径,
  生成默认任务请求,
  读取系统设置,
} from '../../utils/settings'

const 开关项: Array<[keyof 创建任务请求['pipeline'], string]> = [
  ['run_preflight', '执行预检查'],
  ['run_video_extract', '执行视频抽帧'],
  ['run_augmentation', '执行数据增强'],
  ['run_colmap', '执行 COLMAP'],
  ['run_convert', '执行转换'],
  ['run_train', '执行训练'],
  ['run_render', '执行渲染'],
  ['run_metrics', '执行评测'],
  ['launch_viewer', '启动查看器'],
]

function 构建校验信息(表单: 创建任务请求) {
  const messages: string[] = []

  if (!表单.scene.scene_name.trim()) messages.push('场景名称不能为空。')

  if (表单.pipeline.input_mode === 'video' && !表单.scene.video_path.trim()) {
    messages.push('当前为视频模式，视频路径不能为空。')
  }

  if (表单.pipeline.input_mode === 'images' && !表单.scene.raw_image_path.trim()) {
    messages.push('当前为图片模式，原始图片目录不能为空。')
  }

  if (!表单.scene.processed_scene_path.trim()) messages.push('处理目录不能为空。')
  if (!表单.scene.source_path.trim()) messages.push('训练输入目录不能为空。')
  if (!表单.scene.model_output.trim()) messages.push('模型输出目录不能为空。')
  if (表单.train.iterations <= 0) messages.push('训练轮数必须大于 0。')
  if (表单.train.extra_args.resolution <= 0) messages.push('分辨率倍率必须大于 0。')

  if (!表单.pipeline.run_train && (表单.pipeline.run_render || 表单.pipeline.run_metrics)) {
    messages.push('未启用训练时，不建议直接启用渲染或评测。')
  }

  return messages
}

export function TaskCreatePage() {
  const navigate = useNavigate()
  const 系统设置 = useMemo(() => 读取系统设置(), [])
  const [表单, set表单] = useState<创建任务请求>(() => 生成默认任务请求(系统设置))
  const [提交中, set提交中] = useState(false)
  const [错误, set错误] = useState('')
  const [提示, set提示] = useState('')

  const 校验信息 = useMemo(() => 构建校验信息(表单), [表单])

  const 当前输入模式说明 =
    表单.pipeline.input_mode === 'video'
      ? '当前为视频模式，系统优先读取视频路径，通常配合“视频抽帧”流程使用。'
      : '当前为图片模式，系统直接读取原始图片目录。'

  const 模板摘要 = `当前模板：${表单.train.active_profile}，训练轮数：${表单.train.iterations}，分辨率倍率：${表单.train.extra_args.resolution}，数据设备：${表单.train.extra_args.data_device}`

  const 刷新路径 = (sceneName: string) => {
    set表单((prev) => 根据场景名更新路径(prev, 系统设置, sceneName))
  }

  const 应用模板 = (template: 'fast' | 'normal' | 'low_vram') => {
    set表单((prev) => {
      if (template === 'fast') {
        return {
          ...prev,
          train: {
            ...prev.train,
            active_profile: 'fast_preview',
            iterations: 7000,
            save_iterations: [2000, 7000],
            test_iterations: [-1],
            checkpoint_iterations: [2000, 7000],
            start_checkpoint: '',
            resume_from_latest: false,
            quiet: false,
            extra_args: {
              ...prev.train.extra_args,
              resolution: 8,
              data_device: 'cpu',
              densify_grad_threshold: 0.001,
              densification_interval: 300,
              densify_until_iter: 1500,
            },
          },
          pipeline: {
            ...prev.pipeline,
            run_train: true,
            run_render: true,
            run_metrics: false,
          },
        }
      }

      if (template === 'normal') {
        return {
          ...prev,
          train: {
            ...prev.train,
            active_profile: 'normal',
            iterations: 30000,
            save_iterations: [7000, 30000],
            test_iterations: [-1],
            checkpoint_iterations: [2000, 15000, 30000],
            start_checkpoint: '',
            resume_from_latest: false,
            quiet: false,
            extra_args: {
              ...prev.train.extra_args,
              resolution: 4,
              data_device: 'cuda',
              densify_grad_threshold: 0.001,
              densification_interval: 200,
              densify_until_iter: 3000,
            },
          },
          pipeline: {
            ...prev.pipeline,
            run_train: true,
            run_render: true,
            run_metrics: true,
          },
        }
      }

      return {
        ...prev,
        train: {
          ...prev.train,
          active_profile: 'low_vram',
          iterations: 30000,
          save_iterations: [7000, 30000],
          test_iterations: [-1],
          checkpoint_iterations: [2000, 15000, 30000],
          start_checkpoint: '',
          resume_from_latest: false,
          quiet: false,
          extra_args: {
            ...prev.train.extra_args,
            resolution: 4,
            data_device: 'cpu',
            densify_grad_threshold: 0.001,
            densification_interval: 200,
            densify_until_iter: 3000,
          },
        },
        pipeline: {
          ...prev.pipeline,
          run_train: true,
          run_render: true,
          run_metrics: true,
        },
      }
    })

    set提示('模板参数已应用。')
    set错误('')
    window.setTimeout(() => set提示(''), 1500)
  }

  const 重新载入默认值 = () => {
    set表单(生成默认任务请求(系统设置))
    set提示('已重新载入系统默认值。')
    set错误('')
    window.setTimeout(() => set提示(''), 1500)
  }

  const 提交 = async () => {
    if (校验信息.length) {
      set错误(校验信息[0])
      return
    }

    try {
      set提交中(true)
      set错误('')
      set提示('')

      const 已创建 = await 创建任务(表单)

      // 不再等待启动接口完成后才跳转，避免后端热重载或子进程启动较慢时页面一直停在“正在提交”。
      // 进入运行页后会轮询任务状态；启动失败时，运行页仍可看到已创建的任务记录。
      启动任务(已创建.task_id).catch((error) => {
        console.error('启动任务失败：', error)
      })

      navigate(`/tasks/${已创建.task_id}`)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '创建任务失败')
    } finally {
      set提交中(false)
    }
  }

  return (
    <div className="page task-create-page">
      <div className="page-header">
        <div>
          <h1>新建任务</h1>
          <p className="page-subtitle">
            本页会自动读取系统设置中的默认路径和工具配置，可根据需要调整参数后创建任务。
          </p>
        </div>
        <div className="inline-actions">
          <button type="button" className="ghost-btn" onClick={重新载入默认值}>
            重新载入默认值
          </button>
        </div>
      </div>

      {提示 ? <div className="success-box">{提示}</div> : null}
      {错误 ? <div className="error-box">{错误}</div> : null}

      <div className="card">
        <div className="toolbar-row">
          <div>
            <h3>快速模板</h3>
            <p className="section-tip">可通过预设模板快速加载常用训练参数，减少重复输入。</p>
          </div>
          <div className="inline-actions wrap-actions">
            <button type="button" className="ghost-btn" onClick={() => 应用模板('fast')}>
              快速预览
            </button>
            <button type="button" className="ghost-btn" onClick={() => 应用模板('normal')}>
              标准训练
            </button>
            <button type="button" className="ghost-btn" onClick={() => 应用模板('low_vram')}>
              低显存
            </button>
          </div>
        </div>
        <div className="light-tip" style={{ marginTop: 12 }}>
          {模板摘要}
        </div>
      </div>

      <div className="form-grid">
        <div className="card span-2">
          <h3>基础信息</h3>
          <div className="field-grid two-columns">
            <div>
              <label>场景名称</label>
              <input
                value={表单.scene.scene_name}
                onChange={(e) => {
                  const value = e.target.value
                  if (系统设置.sceneDefaults.autoFillPaths) {
                    刷新路径(value)
                  } else {
                    set表单((prev) => ({
                      ...prev,
                      scene: {
                        ...prev.scene,
                        scene_name: value,
                      },
                    }))
                  }
                }}
              />
            </div>

            <div>
              <label>输入模式</label>
              <select
                value={表单.pipeline.input_mode}
                onChange={(e) => {
                  const value = e.target.value as 'images' | 'video'
                  set表单((prev) => ({
                    ...prev,
                    pipeline: {
                      ...prev.pipeline,
                      input_mode: value,
                      run_video_extract: value === 'video' ? true : prev.pipeline.run_video_extract,
                    },
                  }))
                }}
              >
                <option value="images">图片</option>
                <option value="video">视频</option>
              </select>
            </div>
          </div>

          <div className="inline-actions wrap-actions">
            <button
              type="button"
              className="ghost-btn"
              onClick={() => 刷新路径(表单.scene.scene_name)}
            >
              根据场景名重算路径
            </button>
            <span className="light-tip">{当前输入模式说明}</span>
          </div>
        </div>

        <div className="card span-2">
          <h3>数据路径</h3>
          <div className="field-grid two-columns">
            <div>
              <label>原始图片目录</label>
              <input
                value={表单.scene.raw_image_path}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      raw_image_path: e.target.value,
                    },
                  }))
                }
                disabled={表单.pipeline.input_mode === 'video'}
              />
            </div>

            <div>
              <label>视频路径</label>
              <input
                value={表单.scene.video_path}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      video_path: e.target.value,
                    },
                  }))
                }
                disabled={表单.pipeline.input_mode === 'images'}
              />
            </div>

            <div>
              <label>处理目录</label>
              <input
                value={表单.scene.processed_scene_path}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      processed_scene_path: e.target.value,
                    },
                  }))
                }
              />
            </div>

            <div>
              <label>训练输入目录</label>
              <input
                value={表单.scene.source_path}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      source_path: e.target.value,
                    },
                  }))
                }
              />
            </div>

            <div className="full-width">
              <label>模型输出目录</label>
              <input
                value={表单.scene.model_output}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      model_output: e.target.value,
                    },
                  }))
                }
              />
            </div>
          </div>
        </div>

        <div className="card">
          <h3>训练参数</h3>
          <div className="field-grid">
            <div>
              <label>训练模板</label>
              <input
                value={表单.train.active_profile}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    train: {
                      ...prev.train,
                      active_profile: e.target.value,
                    },
                  }))
                }
              />
            </div>

            <div>
              <label>训练轮数</label>
              <input
                type="number"
                min={1}
                value={表单.train.iterations}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    train: {
                      ...prev.train,
                      iterations: Number(e.target.value) || 1,
                    },
                  }))
                }
              />
            </div>

            <div>
              <label>分辨率倍率</label>
              <input
                type="number"
                min={1}
                value={表单.train.extra_args.resolution}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    train: {
                      ...prev.train,
                      extra_args: {
                        ...prev.train.extra_args,
                        resolution: Number(e.target.value) || 1,
                      },
                    },
                  }))
                }
              />
            </div>

            <div>
              <label>数据设备</label>
              <input
                value={表单.train.extra_args.data_device}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    train: {
                      ...prev.train,
                      extra_args: {
                        ...prev.train.extra_args,
                        data_device: e.target.value,
                      },
                    },
                  }))
                }
              />
            </div>
          </div>
        </div>

        <div className="card">
          <h3>工具路径</h3>
          <div className="field-grid">
            <div>
              <label>COLMAP</label>
              <input
                value={表单.scene.colmap_executable}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      colmap_executable: e.target.value,
                    },
                  }))
                }
              />
            </div>

            <div>
              <label>FFmpeg</label>
              <input
                value={表单.scene.ffmpeg_executable}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      ffmpeg_executable: e.target.value,
                    },
                  }))
                }
              />
            </div>

            <div>
              <label>ImageMagick</label>
              <input
                value={表单.scene.magick_executable}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      magick_executable: e.target.value,
                    },
                  }))
                }
              />
            </div>

            <div>
              <label>Viewer 根目录</label>
              <input
                value={表单.scene.viewer_root}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    scene: {
                      ...prev.scene,
                      viewer_root: e.target.value,
                    },
                  }))
                }
              />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="toolbar-row">
          <div>
            <h3>流程开关</h3>
            <p className="section-tip">可根据实际需要启用或关闭对应处理流程。</p>
          </div>
        </div>

        <div className="flag-grid compact-flag-grid">
          {开关项.map(([字段, 标签]) => (
            <label key={字段} className="flag-card compact-flag-card">
              <input
                type="checkbox"
                checked={Boolean(表单.pipeline[字段])}
                onChange={(e) =>
                  set表单((prev) => ({
                    ...prev,
                    pipeline: {
                      ...prev.pipeline,
                      [字段]: e.target.checked,
                    },
                  }))
                }
              />
              <span>{标签}</span>
            </label>
          ))}
        </div>
      </div>

      {校验信息.length ? (
        <div className="warning-box">
          <strong>提交前提示：</strong>
          <ul>
            {校验信息.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <button type="button" className="primary-btn" onClick={提交} disabled={提交中}>
        {提交中 ? '正在提交' : '创建并启动任务'}
      </button>
    </div>
  )
}