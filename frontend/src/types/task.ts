export type 任务状态 =
  | 'created'
  | 'queued'
  | 'running'
  | 'stopping'
  | 'stopped'
  | 'success'
  | 'failed'
  | 'retrying'
  | 'partial_success'

export type 阶段状态 =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'stopped'

export interface 阶段记录 {
  stage_key: string
  stage_label: string
  order: number
  status: 阶段状态 | string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  error_type: string | null
  error_message: string | null
}

export interface 系统路径配置 {
  gs_repo: string
  raw_data: string
  processed_data: string
  outputs: string
  logs: string
  videos_data: string
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
      [key: string]: string | number | boolean | null
    }
  }
}

export interface 任务响应 {
  task_id: string
  scene_name: string
  status: 任务状态 | string
  current_stage: string
  message: string
  result: Record<string, unknown>
  error: string | null

  created_at: string | null
  started_at: string | null
  finished_at: string | null

  stop_requested: boolean
  retry_count: number

  stage_history: 阶段记录[]
  metrics_summary: Record<string, unknown>
  result_files: Record<string, unknown>
}

export interface 任务动作响应 {
  ok: boolean
  task_id: string
  action: 'stop' | 'retry' | 'delete'
  status: 任务状态 | string
  message: string
}

export interface 任务列表响应 {
  items: 任务响应[]
}

export interface 结果响应 {
  task_id: string
  scene_name: string
  status: 任务状态 | string
  current_stage: string
  message: string
  error: string | null

  created_at: string | null
  started_at: string | null
  finished_at: string | null

  stop_requested: boolean
  retry_count: number

  stage_history: 阶段记录[]
  metrics_summary: Record<string, unknown>
  result_files: Record<string, unknown>
  result: Record<string, unknown>
}