export type 任务状态 = 'created' | 'queued' | 'running' | 'success' | 'failed'

export interface 系统路径配置 {
  gs_repo: string
  raw_data: string
  processed_data: string
  outputs: string
  logs: string
  videos_data: string
}

export interface 任务响应 {
  task_id: string
  scene_name: string
  status: 任务状态 | string
  current_stage: string
  message: string
  result: Record<string, unknown>
  error?: string | null
}

export interface 结果响应 {
  task_id: string
  status: string
  scene_name: string
  result: Record<string, unknown>
  error?: string | null
}

export interface 创建任务请求 {
  scene: {
    scene_name: string
    raw_image_path: string
    processed_scene_path: string
    source_path: string
    model_output: string
    video_path: string
    colmap_executable: string
    magick_executable: string
    ffmpeg_executable: string
    viewer_root: string
  }
  system_paths: 系统路径配置
  pipeline: {
    input_mode: 'images' | 'video'
    run_preflight: boolean
    run_video_extract: boolean
    run_colmap: boolean
    run_convert: boolean
    run_train: boolean
    run_render: boolean
    run_metrics: boolean
    launch_viewer: boolean
  }
  train: {
    active_profile: string
    eval: boolean
    iterations: number
    save_iterations: number[]
    test_iterations: number[]
    checkpoint_iterations: number[]
    start_checkpoint: string
    resume_from_latest: boolean
    quiet: boolean
    extra_args: {
      data_device: string
      resolution: number
      densify_grad_threshold: number
      densification_interval: number
      densify_until_iter: number
    }
  }
}
