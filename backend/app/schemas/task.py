from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


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
    checkpoint_iterations: List[int] = Field(default_factory=lambda: [2000, 15000, 30000])
    start_checkpoint: str = ""
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


class TaskResponse(BaseModel):
    task_id: str
    scene_name: str
    status: str
    current_stage: str
    message: str
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None