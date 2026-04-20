import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { 创建任务, 启动任务 } from '../../api/task'
import type { 创建任务请求 } from '../../types/task'

const 初始值: 创建任务请求 = {
  scene: {
    scene_name: 'video_scene_01',
    raw_image_path: 'datasets/raw/video_scene_01/images',
    processed_scene_path: 'datasets/processed/video_scene_01',
    source_path: 'datasets/processed/video_scene_01/gs_input',
    model_output: 'outputs/video_scene_01',
    video_path: 'datasets/videos/video_scene_01.mp4',
    colmap_executable: 'third_party/colmap/COLMAP.bat',
    magick_executable: '',
    ffmpeg_executable: 'ffmpeg',
    viewer_root: 'third_party/viewer/bin',
  },
  pipeline: {
    input_mode: 'images',
    run_preflight: true,
    run_video_extract: false,
    run_colmap: true,
    run_convert: true,
    run_train: true,
    run_render: true,
    run_metrics: true,
    launch_viewer: false,
  },
  train: {
    active_profile: 'low_vram',
    eval: true,
    iterations: 30000,
    save_iterations: [7000, 30000],
    test_iterations: [-1],
    checkpoint_iterations: [2000, 15000, 30000],
    start_checkpoint: '',
    resume_from_latest: false,
    quiet: false,
    extra_args: {
      data_device: 'cpu',
      resolution: 4,
      densify_grad_threshold: 0.001,
      densification_interval: 200,
      densify_until_iter: 3000,
    },
  },
}

export function TaskCreatePage() {
  const [表单, set表单] = useState<创建任务请求>(初始值)
  const [提交中, set提交中] = useState(false)
  const [错误, set错误] = useState('')
  const navigate = useNavigate()

  const 提交 = async () => {
    try {
      set提交中(true)
      set错误('')
      const 已创建 = await 创建任务(表单)
      await 启动任务(已创建.task_id)
      navigate(`/tasks/${已创建.task_id}`)
    } catch (error) {
      set错误(error instanceof Error ? error.message : '创建失败')
    } finally {
      set提交中(false)
    }
  }

  return (
    <div className="page">
      <h1>新建任务</h1>
      <div className="form-grid">
        <label>
          <span>场景名称</span>
          <input value={表单.scene.scene_name} onChange={(e) => set表单({ ...表单, scene: { ...表单.scene, scene_name: e.target.value } })} />
        </label>
        <label>
          <span>输入模式</span>
          <select value={表单.pipeline.input_mode} onChange={(e) => set表单({ ...表单, pipeline: { ...表单.pipeline, input_mode: e.target.value as 'images' | 'video' } })}>
            <option value="images">图片</option>
            <option value="video">视频</option>
          </select>
        </label>
        <label>
          <span>原始图片目录</span>
          <input value={表单.scene.raw_image_path} onChange={(e) => set表单({ ...表单, scene: { ...表单.scene, raw_image_path: e.target.value } })} />
        </label>
        <label>
          <span>处理目录</span>
          <input value={表单.scene.processed_scene_path} onChange={(e) => set表单({ ...表单, scene: { ...表单.scene, processed_scene_path: e.target.value } })} />
        </label>
        <label>
          <span>训练输入目录</span>
          <input value={表单.scene.source_path} onChange={(e) => set表单({ ...表单, scene: { ...表单.scene, source_path: e.target.value } })} />
        </label>
        <label>
          <span>模型输出目录</span>
          <input value={表单.scene.model_output} onChange={(e) => set表单({ ...表单, scene: { ...表单.scene, model_output: e.target.value } })} />
        </label>
        <label>
          <span>视频路径</span>
          <input value={表单.scene.video_path} onChange={(e) => set表单({ ...表单, scene: { ...表单.scene, video_path: e.target.value } })} />
        </label>
        <label>
          <span>训练轮数</span>
          <input type="number" value={表单.train.iterations} onChange={(e) => set表单({ ...表单, train: { ...表单.train, iterations: Number(e.target.value) } })} />
        </label>
        <label>
          <span>训练模式</span>
          <input value={表单.train.active_profile} onChange={(e) => set表单({ ...表单, train: { ...表单.train, active_profile: e.target.value } })} />
        </label>
        <label>
          <span>分辨率倍率</span>
          <input type="number" value={表单.train.extra_args.resolution} onChange={(e) => set表单({ ...表单, train: { ...表单.train, extra_args: { ...表单.train.extra_args, resolution: Number(e.target.value) } } })} />
        </label>
      </div>

      <div className="checkbox-grid">
        {[
          ['run_preflight', '执行预检查'],
          ['run_video_extract', '执行视频抽帧'],
          ['run_colmap', '执行 COLMAP'],
          ['run_convert', '执行转换'],
          ['run_train', '执行训练'],
          ['run_render', '执行渲染'],
          ['run_metrics', '执行评测'],
          ['launch_viewer', '启动查看器'],
        ].map(([字段, 标签]) => (
          <label key={字段} className="checkbox-item">
            <input
              type="checkbox"
              checked={Boolean(表单.pipeline[字段 as keyof typeof 表单.pipeline])}
              onChange={(e) =>
                set表单({
                  ...表单,
                  pipeline: { ...表单.pipeline, [字段]: e.target.checked },
                })
              }
            />
            <span>{标签}</span>
          </label>
        ))}
      </div>

      {错误 ? <div className="error-box">{错误}</div> : null}

      <button className="primary-btn" onClick={提交} disabled={提交中}>
        {提交中 ? '正在提交' : '创建并启动任务'}
      </button>
    </div>
  )
}
