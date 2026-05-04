from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

TaskStatus = Literal[
    "created",
    "queued",
    "running",
    "stopping",
    "stopped",
    "success",
    "failed",
    "retrying",
    "partial_success",
]


class SystemPaths(BaseModel):
    gs_repo: str = "third_party/gaussian-splatting"
    raw_data: str = "datasets/raw"
    processed_data: str = "datasets/processed"
    outputs: str = "outputs"
    logs: str = "logs"
    videos_data: str = "datasets/videos"


class PipelineFlags(BaseModel):
    input_mode: Literal["images", "video"] = "images"
    run_preflight: bool = True
    run_video_extract: bool = False
    run_colmap: bool = True
    run_convert: bool = True
    run_train: bool = True
    run_render: bool = True
    run_metrics: bool = True
    launch_viewer: bool = False


class TrainProfile(BaseModel):
    active_profile: str = "low_vram"
    eval: bool = True
    iterations: int = 30000
    save_iterations: List[int] = Field(default_factory=lambda: [7000, 30000])
    test_iterations: List[int] = Field(default_factory=lambda: [-1])
    checkpoint_iterations: List[int] = Field(
        default_factory=lambda: [2000, 15000, 30000]
    )
    start_checkpoint: Optional[str] = ""
    resume_from_latest: bool = False
    quiet: bool = False
    extra_args: Dict[str, Any] = Field(
        default_factory=lambda: {
            "data_device": "cpu",
            "resolution": 4,
            "densify_grad_threshold": 0.001,
            "densification_interval": 200,
            "densify_until_iter": 3000,
        }
    )

class SceneConfig(BaseModel):
    scene_name: str
    raw_image_path: str = ""
    processed_scene_path: str = ""
    source_path: str = ""
    model_output: str = ""
    video_path: str = ""
    colmap_executable: str = "colmap"
    magick_executable: str = ""
    ffmpeg_executable: str = "ffmpeg"
    viewer_root: str = "third_party/viewer/bin"


class TaskCreateRequest(BaseModel):
    scene: SceneConfig
    system_paths: SystemPaths = Field(default_factory=SystemPaths)
    pipeline: PipelineFlags = Field(default_factory=PipelineFlags)
    train: TrainProfile = Field(default_factory=TrainProfile)


class StageRecord(BaseModel):
    stage_key: str
    stage_label: str
    order: int = 0
    status: Literal["pending", "running", "success", "failed", "stopped"] = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class TaskResponse(BaseModel):
    task_id: str
    scene_name: str
    status: Union[TaskStatus, str]
    current_stage: str
    message: str
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    stop_requested: bool = False
    retry_count: int = 0

    stage_history: List[StageRecord] = Field(default_factory=list)
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    result_files: Dict[str, Any] = Field(default_factory=dict)


class TaskActionResponse(BaseModel):
    ok: bool = True
    task_id: str
    action: Literal["stop", "retry", "delete"]
    status: Union[TaskStatus, str]
    message: str

class TaskLogResponse(BaseModel):
    task_id: str
    lines: List[str] = Field(default_factory=list)
    count: int = 0
