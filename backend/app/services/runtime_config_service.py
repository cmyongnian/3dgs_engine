from pathlib import Path
from typing import Any, Dict

import yaml


class RuntimeConfigService:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.runtime_root = self.project_root / "backend" / "runtime"

    def _to_dict(self, payload: Any) -> Dict[str, Any]:
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        if hasattr(payload, "dict"):
            return payload.dict()
        if isinstance(payload, dict):
            return payload
        raise TypeError("不支持的任务配置类型")

    def _write_yaml(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data,
                f,
                allow_unicode=True,
                sort_keys=False,
            )

    def build(self, task_id: str, payload: Any) -> Dict[str, str]:
        data = self._to_dict(payload)

        scene = data.get("scene", {})
        system_paths = data.get("system_paths", {})
        pipeline = data.get("pipeline", {})
        train = data.get("train", {})

        scene_name = scene.get("scene_name", "default_scene")
        runtime_dir = self.runtime_root / task_id
        runtime_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "task_id": task_id,
            "runtime_dir": str(runtime_dir),
            "system": str(runtime_dir / "system.yaml"),
            "pipeline": str(runtime_dir / "pipeline.yaml"),
            "train": str(runtime_dir / "train.yaml"),
            "render": str(runtime_dir / "render.yaml"),
            "metrics": str(runtime_dir / "metrics.yaml"),
            "preflight": str(runtime_dir / "preflight.yaml"),
            "colmap": str(runtime_dir / "colmap.yaml"),
            "convert": str(runtime_dir / "convert.yaml"),
            "viewer": str(runtime_dir / "viewer.yaml"),
            "video": str(runtime_dir / "video.yaml"),
            "report": str(runtime_dir / "report.yaml"),
        }

        output_dir = scene.get("model_output", "")
        processed_scene_path = scene.get("processed_scene_path", "")
        source_path = scene.get("source_path", "")
        raw_image_path = scene.get("raw_image_path", "")
        video_path = scene.get("video_path", "")

        log_dir = str((self.project_root / "engine" / "logs" / scene_name).resolve())

        system_yaml = {
            "paths": {
                "project_root": str(self.project_root),
                "gs_repo": system_paths.get("gs_repo", "third_party/gaussian-splatting"),
                "raw_data": system_paths.get("raw_data", "datasets/raw"),
                "processed_data": system_paths.get("processed_data", "datasets/processed"),
                "outputs": system_paths.get("outputs", "outputs"),
                "logs": system_paths.get("logs", "logs"),
                "videos_data": system_paths.get("videos_data", "datasets/videos"),
            }
        }

        pipeline_yaml = {
            "pipeline": {
                "input_mode": pipeline.get("input_mode", "images"),
                "run_preflight": pipeline.get("run_preflight", True),
                "run_video_extract": pipeline.get("run_video_extract", False),
                "run_colmap": pipeline.get("run_colmap", True),
                "run_convert": pipeline.get("run_convert", True),
                "run_train": pipeline.get("run_train", True),
                "run_render": pipeline.get("run_render", True),
                "run_metrics": pipeline.get("run_metrics", True),
                "launch_viewer": pipeline.get("launch_viewer", False),
            }
        }

        train_yaml = {
            "train": {
                "scene_name": scene_name,
                "source_path": source_path,
                "model_output": output_dir,
                "active_profile": train.get("active_profile", "low_vram"),
                "profiles": {
                    "low_vram": {
                        "eval": True,
                        "iterations": 30000,
                        "save_iterations": [7000, 30000],
                        "test_iterations": [-1],
                        "checkpoint_iterations": [2000, 15000, 30000],
                        "start_checkpoint": "",
                        "resume_from_latest": False,
                        "quiet": False,
                        "extra_args": {
                            "data_device": "cpu",
                            "resolution": 4,
                            "densify_grad_threshold": 0.001,
                            "densification_interval": 200,
                            "densify_until_iter": 3000,
                        },
                    },
                    "normal": {
                        "eval": True,
                        "iterations": 15000,
                        "save_iterations": [7000, 15000],
                        "test_iterations": [7000, 15000],
                        "checkpoint_iterations": [7000, 15000],
                        "start_checkpoint": "",
                        "resume_from_latest": False,
                        "quiet": False,
                        "extra_args": {
                            "resolution": 2,
                        },
                    },
                    "fast_preview": {
                        "eval": False,
                        "iterations": 3000,
                        "save_iterations": [1000, 3000],
                        "test_iterations": [-1],
                        "checkpoint_iterations": [1000, 3000],
                        "start_checkpoint": "",
                        "resume_from_latest": False,
                        "quiet": False,
                        "extra_args": {
                            "data_device": "cpu",
                            "resolution": 8,
                            "densify_grad_threshold": 0.001,
                            "densification_interval": 250,
                            "densify_until_iter": 1500,
                        },
                    },
                },
            }
        }

        render_yaml = {
            "render": {
                "scene_name": scene_name,
                "model_paths": [output_dir] if output_dir else [],
                "quiet": train.get("quiet", False),
            }
        }

        metrics_yaml = {
            "metrics": {
                "scene_name": scene_name,
                "model_paths": [output_dir] if output_dir else [],
                "processed_scene_path": processed_scene_path,
                "render_dir": output_dir,
                "log_dir": log_dir,
                "collect_colmap_stats": True,
                "collect_resource_stats": True,
                "collect_gaussian_stats": True,
                "collect_preview_images": True,
                "quiet": train.get("quiet", False),
            }
        }

        report_yaml = {
            "report": {
                "scene_name": scene_name,
                "model_paths": [output_dir] if output_dir else [],
                "report_dir": output_dir,
                "log_dir": log_dir,
                "processed_scene_path": processed_scene_path,
                "quiet": train.get("quiet", False),
            }
        }

        preflight_yaml = {
            "preflight": {
                "scene_name": scene_name,
                "input_mode": pipeline.get("input_mode", "images"),
                "raw_image_path": raw_image_path,
                "processed_image_path": source_path,
                "source_path": source_path,
                "video_path": video_path,
                "model_output": output_dir,
                "quiet": train.get("quiet", False),
            }
        }

        colmap_yaml = {
            "colmap": {
                "scene_name": scene_name,
                "image_path": raw_image_path,
                "raw_image_path": raw_image_path,
                "workspace_path": processed_scene_path,
                "processed_scene_path": processed_scene_path,
                "source_path": source_path,
                "colmap_executable": scene.get("colmap_executable", "colmap"),
                "quiet": train.get("quiet", False),
            }
        }

        convert_yaml = {
            "convert": {
                "scene_name": scene_name,
                "source_images": raw_image_path,
                "colmap_workspace": processed_scene_path,
                "gs_input_path": source_path,
                "colmap_executable": scene.get("colmap_executable", ""),
                "magick_executable": scene.get("magick_executable", ""),
                "skip_matching": True,
                "resize": False,
                "use_magick": bool(scene.get("magick_executable", "")),
                "gs_repo": system_paths.get("gs_repo", "third_party/gaussian-splatting"),
                "quiet": train.get("quiet", False),
            }
        }

        viewer_yaml = {
            "viewer": {
                "scene_name": scene_name,
                "model_path": output_dir,
                "viewer_root": scene.get("viewer_root", "third_party/viewer/bin"),
                "quiet": train.get("quiet", False),
            }
        }

        video_yaml = {
            "video": {
                "scene_name": scene_name,
                "video_path": video_path,
                "output_images": raw_image_path,
                "ffmpeg_executable": scene.get("ffmpeg_executable", "ffmpeg"),
                "target_fps": 2,
                "quiet": train.get("quiet", False),
            }
        }

        self._write_yaml(Path(files["system"]), system_yaml)
        self._write_yaml(Path(files["pipeline"]), pipeline_yaml)
        self._write_yaml(Path(files["train"]), train_yaml)
        self._write_yaml(Path(files["render"]), render_yaml)
        self._write_yaml(Path(files["metrics"]), metrics_yaml)
        self._write_yaml(Path(files["report"]), report_yaml)
        self._write_yaml(Path(files["preflight"]), preflight_yaml)
        self._write_yaml(Path(files["colmap"]), colmap_yaml)
        self._write_yaml(Path(files["convert"]), convert_yaml)
        self._write_yaml(Path(files["viewer"]), viewer_yaml)
        self._write_yaml(Path(files["video"]), video_yaml)

        return files


runtime_config_service = RuntimeConfigService()