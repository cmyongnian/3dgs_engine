from __future__ import annotations

from pathlib import Path

import yaml

from backend.app.schemas.task import TaskCreateRequest


class RuntimeConfigService:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.engine_root = self.project_root / "engine"
        self.runtime_root = self.engine_root / "configs" / "runtime"

    def build(self, task_id: str, payload: TaskCreateRequest) -> dict[str, str]:
        scene = payload.scene
        system_paths = payload.system_paths
        pipeline = payload.pipeline
        train = payload.train

        runtime_dir = self.runtime_root / task_id
        runtime_dir.mkdir(parents=True, exist_ok=True)

        scene_name = scene.scene_name
        raw_image_path = scene.raw_image_path or f"datasets/raw/{scene_name}/images"
        processed_scene_path = scene.processed_scene_path or f"datasets/processed/{scene_name}"
        source_path = scene.source_path or f"{processed_scene_path}/gs_input"
        model_output = scene.model_output or f"outputs/{scene_name}"
        video_path = scene.video_path or f"datasets/videos/{scene_name}.mp4"
        colmap_workspace = f"{processed_scene_path}/colmap_workspace"

        files = {
            "system": runtime_dir / "system.yaml",
            "pipeline": runtime_dir / "pipeline.yaml",
            "train": runtime_dir / "train.yaml",
            "render": runtime_dir / "render.yaml",
            "metrics": runtime_dir / "metrics.yaml",
            "preflight": runtime_dir / "preflight.yaml",
            "colmap": runtime_dir / "colmap.yaml",
            "convert": runtime_dir / "convert.yaml",
            "viewer": runtime_dir / "viewer.yaml",
            "video": runtime_dir / "video.yaml",
        }

        self._dump(
            files["system"],
            {
                "project_name": "3dgs_platform",
                "paths": {
                    "gs_repo": system_paths.gs_repo,
                    "raw_data": system_paths.raw_data,
                    "processed_data": system_paths.processed_data,
                    "outputs": system_paths.outputs,
                    "logs": system_paths.logs,
                    "videos_data": system_paths.videos_data,
                },
                "runtime": {"python_env": "3dgs1", "device": "cuda"},
            },
        )

        self._dump(
            files["pipeline"],
            {
                "pipeline": {
                    "input_mode": pipeline.input_mode,
                    "run_preflight": pipeline.run_preflight,
                    "run_video_extract": pipeline.run_video_extract,
                    "run_colmap": pipeline.run_colmap,
                    "run_convert": pipeline.run_convert,
                    "run_train": pipeline.run_train,
                    "run_render": pipeline.run_render,
                    "run_metrics": pipeline.run_metrics,
                    "launch_viewer": pipeline.launch_viewer,
                }
            },
        )

        self._dump(
            files["train"],
            {
                "train": {
                    "scene_name": scene_name,
                    "source_path": source_path,
                    "model_output": model_output,
                    "active_profile": train.active_profile,
                    "profiles": {
                        train.active_profile: {
                            "eval": train.eval,
                            "iterations": train.iterations,
                            "save_iterations": train.save_iterations,
                            "test_iterations": train.test_iterations,
                            "checkpoint_iterations": train.checkpoint_iterations,
                            "start_checkpoint": train.start_checkpoint,
                            "resume_from_latest": train.resume_from_latest,
                            "quiet": train.quiet,
                            "extra_args": train.extra_args,
                        }
                    },
                }
            },
        )

        self._dump(
            files["render"],
            {
                "render": {
                    "scene_name": scene_name,
                    "model_path": model_output,
                    "iteration": -1,
                    "skip_train": True,
                    "skip_test": False,
                    "quiet": False,
                }
            },
        )

        self._dump(
            files["metrics"],
            {"metrics": {"scene_name": scene_name, "model_paths": [model_output], "quiet": False}},
        )

        self._dump(
            files["preflight"],
            {
                "preflight": {
                    "scene_name": scene_name,
                    "raw_image_path": raw_image_path,
                    "processed_image_path": f"{source_path}/images",
                    "min_images": 10,
                    "blur_threshold": 100.0,
                    "fail_on_unreadable": True,
                }
            },
        )

        self._dump(
            files["colmap"],
            {
                "colmap": {
                    "scene_name": scene_name,
                    "image_path": raw_image_path,
                    "workspace_path": colmap_workspace,
                    "colmap_executable": scene.colmap_executable,
                    "use_gpu": True,
                }
            },
        )

        self._dump(
            files["convert"],
            {
                "convert": {
                    "scene_name": scene_name,
                    "source_images": raw_image_path,
                    "colmap_workspace": colmap_workspace,
                    "gs_input_path": source_path,
                    "gs_repo": system_paths.gs_repo,
                    "colmap_executable": scene.colmap_executable,
                    "skip_matching": True,
                    "resize": False,
                    "use_magick": False,
                    "magick_executable": scene.magick_executable,
                }
            },
        )

        self._dump(
            files["viewer"],
            {
                "viewer": {
                    "mode": "realtime",
                    "viewer_root": scene.viewer_root,
                    "model_path": model_output,
                    "source_path": processed_scene_path,
                    "rendering_width": 1200,
                    "rendering_height": 800,
                    "force_aspect_ratio": False,
                    "load_images": False,
                    "device": 0,
                    "wait_until_close": True,
                    "detached": False,
                }
            },
        )

        self._dump(
            files["video"],
            {
                "video": {
                    "scene_name": scene_name,
                    "video_path": video_path,
                    "output_images": raw_image_path,
                    "ffmpeg_executable": scene.ffmpeg_executable,
                    "target_fps": 2,
                }
            },
        )

        return {name: str(path) for name, path in files.items()}

    @staticmethod
    def _dump(path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


runtime_config_service = RuntimeConfigService()
