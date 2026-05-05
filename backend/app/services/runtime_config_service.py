from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def _as_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _as_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _clamp_int(self, value: Any, default: int, minimum: int, maximum: Optional[int] = None) -> int:
        result = self._as_int(value, default)
        result = max(minimum, result)
        if maximum is not None:
            result = min(maximum, result)
        return result

    def _clamp_float(self, value: Any, default: float, minimum: float, maximum: Optional[float] = None) -> float:
        result = self._as_float(value, default)
        result = max(minimum, result)
        if maximum is not None:
            result = min(maximum, result)
        return result

    def _as_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True
            if lowered in {"0", "false", "no", "n", "off"}:
                return False
        if value is None:
            return default
        return bool(value)

    def _as_int_list(self, value: Any, default: List[int]) -> List[int]:
        if value is None or value == "":
            return list(default)

        if isinstance(value, str):
            items = [item.strip() for item in value.replace("，", ",").split(",")]
        elif isinstance(value, (list, tuple, set)):
            items = list(value)
        else:
            items = [value]

        result: List[int] = []

        for item in items:
            if item is None or item == "":
                continue
            try:
                result.append(int(item))
            except Exception:
                continue

        return result if result else list(default)

    def _clean_extra_args(self, extra_args: Any) -> Dict[str, Any]:
        if not isinstance(extra_args, dict):
            return {}

        cleaned: Dict[str, Any] = {}

        for key, value in extra_args.items():
            if value is None or value == "":
                continue
            cleaned[str(key)] = value

        return cleaned

    def _clean_path_text(self, value: Any, default: str = "") -> str:
        text = str(value or "").strip()
        return text or default

    def _append_task_id_to_path(
        self,
        value: Any,
        task_id: str,
        *,
        default: str = "",
        keep_images_leaf: bool = False,
    ) -> str:
        """
        为每次任务生成独立目录，避免多个任务共用同一个 outputs / processed / raw frames 目录。

        - outputs/video_scene_01  -> outputs/video_scene_01/<task_id>
        - datasets/processed/video_scene_01 -> datasets/processed/video_scene_01/<task_id>
        - datasets/raw/video_scene_01/images + keep_images_leaf=True
          -> datasets/raw/video_scene_01/<task_id>/images
        """
        text = self._clean_path_text(value, default)
        if not text:
            return ""

        path = Path(text)
        parts = [str(part).lower() for part in path.parts]
        if task_id.lower() in parts:
            return str(path)

        if keep_images_leaf and path.name.lower() == "images":
            return str(path.parent / task_id / path.name)

        return str(path / task_id)

    def _build_train_profiles(self, train: Dict[str, Any]) -> Dict[str, Any]:
        """
        将前端提交的训练参数真正写入 active_profile 对应的配置。

        原来的问题是 active_profile 会变化，但 profiles 内部仍然使用写死的默认值，
        导致前端输入的 iterations、resolution、data_device、densification_interval 等
        参数没有真正传给 engine/core/train_service.py。
        """
        default_profiles: Dict[str, Dict[str, Any]] = {
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
                "iterations": 30000,
                "save_iterations": [7000, 30000],
                "test_iterations": [-1],
                "checkpoint_iterations": [2000, 15000, 30000],
                "start_checkpoint": "",
                "resume_from_latest": False,
                "quiet": False,
                "extra_args": {
                    "data_device": "cuda",
                    "resolution": 4,
                    "densify_grad_threshold": 0.001,
                    "densification_interval": 200,
                    "densify_until_iter": 3000,
                },
            },
            "fast_preview": {
                "eval": False,
                "iterations": 7000,
                "save_iterations": [2000, 7000],
                "test_iterations": [-1],
                "checkpoint_iterations": [2000, 7000],
                "start_checkpoint": "",
                "resume_from_latest": False,
                "quiet": False,
                "extra_args": {
                    "data_device": "cpu",
                    "resolution": 8,
                    "densify_grad_threshold": 0.001,
                    "densification_interval": 300,
                    "densify_until_iter": 1500,
                },
            },
        }

        active_profile = str(train.get("active_profile") or "low_vram").strip() or "low_vram"
        base_profile = dict(default_profiles.get(active_profile, default_profiles["low_vram"]))
        base_extra_args = dict(base_profile.get("extra_args", {}))
        submitted_extra_args = self._clean_extra_args(train.get("extra_args", {}))

        submitted_profile = {
            "eval": self._as_bool(train.get("eval"), base_profile.get("eval", True)),
            "iterations": self._as_int(train.get("iterations"), base_profile.get("iterations", 30000)),
            "save_iterations": self._as_int_list(
                train.get("save_iterations"),
                base_profile.get("save_iterations", [7000, 30000]),
            ),
            "test_iterations": self._as_int_list(
                train.get("test_iterations"),
                base_profile.get("test_iterations", [-1]),
            ),
            "checkpoint_iterations": self._as_int_list(
                train.get("checkpoint_iterations"),
                base_profile.get("checkpoint_iterations", [2000, 15000, 30000]),
            ),
            "start_checkpoint": train.get("start_checkpoint") or "",
            "resume_from_latest": self._as_bool(train.get("resume_from_latest"), False),
            "quiet": self._as_bool(train.get("quiet"), False),
            "extra_args": {
                **base_extra_args,
                **submitted_extra_args,
            },
        }

        iterations = max(1, self._as_int(submitted_profile.get("iterations"), 30000))
        submitted_profile["iterations"] = iterations

        save_iterations = [
            item
            for item in self._as_int_list(submitted_profile.get("save_iterations"), [iterations])
            if 0 < item <= iterations
        ]
        if iterations not in save_iterations:
            save_iterations.append(iterations)
        submitted_profile["save_iterations"] = sorted(set(save_iterations))

        checkpoint_iterations = [
            item
            for item in self._as_int_list(
                submitted_profile.get("checkpoint_iterations"), [iterations]
            )
            if 0 < item <= iterations
        ]
        if iterations not in checkpoint_iterations:
            checkpoint_iterations.append(iterations)
        submitted_profile["checkpoint_iterations"] = sorted(set(checkpoint_iterations))

        test_iterations = []
        for item in self._as_int_list(submitted_profile.get("test_iterations"), [-1]):
            if item == -1 or 0 < item <= iterations:
                test_iterations.append(item)
        submitted_profile["test_iterations"] = sorted(set(test_iterations)) or [-1]

        profiles = {key: dict(value) for key, value in default_profiles.items()}
        profiles[active_profile] = submitted_profile

        return {
            "active_profile": active_profile,
            "profiles": profiles,
            "active_profile_data": submitted_profile,
        }

    def build(self, task_id: str, payload: Any) -> Dict[str, str]:
        data = self._to_dict(payload)

        scene = data.get("scene", {})
        system_paths = data.get("system_paths", {})
        pipeline = data.get("pipeline", {})
        augmentation = data.get("augmentation", {})
        train = data.get("train", {})

        scene_name = self._clean_path_text(scene.get("scene_name"), "default_scene")
        input_mode = self._clean_path_text(pipeline.get("input_mode"), "images")

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
            "augmentation": str(runtime_dir / "augmentation.yaml"),
            "report": str(runtime_dir / "report.yaml"),
        }

        # 原始图片目录：图片模式直接使用用户输入；视频抽帧模式需要按任务隔离，避免覆盖旧抽帧。
        raw_image_base = self._clean_path_text(
            scene.get("raw_image_path"),
            "datasets/raw/{0}/images".format(scene_name),
        )
        if input_mode == "video":
            raw_image_path = self._append_task_id_to_path(
                raw_image_base,
                task_id,
                keep_images_leaf=True,
            )
        else:
            raw_image_path = raw_image_base

        # 以下目录必须按 task_id 隔离，否则多个任务会读写同一个 COLMAP / 训练 / report 结果。
        processed_base = self._clean_path_text(
            scene.get("processed_scene_path"),
            "datasets/processed/{0}".format(scene_name),
        )
        processed_scene_path = self._append_task_id_to_path(processed_base, task_id)

        source_path = str(Path(processed_scene_path) / "gs_input")

        output_base = self._clean_path_text(
            scene.get("model_output"),
            "outputs/{0}".format(scene_name),
        )
        output_dir = self._append_task_id_to_path(output_base, task_id)

        video_path = self._clean_path_text(scene.get("video_path"), "")

        augmentation_output_subdir = str(augmentation.get("output_subdir") or "augmented_images").strip() or "augmented_images"
        augmented_image_path = str(Path(processed_scene_path) / augmentation_output_subdir)

        augmentation_enabled = self._as_bool(augmentation.get("enabled", True), True)
        run_augmentation = self._as_bool(pipeline.get("run_augmentation", True), True) and augmentation_enabled
        effective_image_path = augmented_image_path if run_augmentation else raw_image_path

        train_profiles = self._build_train_profiles(train)
        active_profile_data = train_profiles["active_profile_data"]
        quiet = self._as_bool(active_profile_data.get("quiet"), False)

        log_dir = str((self.project_root / "engine" / "logs" / scene_name / task_id).resolve())

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
                "input_mode": input_mode,
                "run_preflight": pipeline.get("run_preflight", True),
                "run_video_extract": pipeline.get("run_video_extract", False),
                "run_augmentation": run_augmentation,
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
                "active_profile": train_profiles["active_profile"],
                "profiles": train_profiles["profiles"],
            }
        }

        render_yaml = {
            "render": {
                "scene_name": scene_name,
                "model_path": output_dir,
                "model_paths": [output_dir] if output_dir else [],
                "quiet": quiet,
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
                "quiet": quiet,
            }
        }

        report_yaml = {
            "report": {
                "scene_name": scene_name,
                "model_paths": [output_dir] if output_dir else [],
                "report_dir": output_dir,
                "log_dir": log_dir,
                "processed_scene_path": processed_scene_path,
                "quiet": quiet,
            }
        }

        preflight_yaml = {
            "preflight": {
                "scene_name": scene_name,
                "input_mode": input_mode,
                "raw_image_path": raw_image_path,
                "processed_image_path": source_path,
                "source_path": source_path,
                "video_path": video_path,
                "model_output": output_dir,
                "quiet": quiet,
            }
        }
        clahe_tile_grid_size = augmentation.get("clahe_tile_grid_size", [8, 8])
        if not isinstance(clahe_tile_grid_size, (list, tuple)) or len(clahe_tile_grid_size) != 2:
            clahe_tile_grid_size = [8, 8]

        augmentation_yaml = {
            "augmentation": {
                "scene_name": scene_name,
                "enabled": run_augmentation,
                "preset": augmentation.get("preset", "safe"),
                "input_images": raw_image_path,
                "output_images": augmented_image_path,
                "log_dir": log_dir,
                "overwrite": self._as_bool(augmentation.get("overwrite", True), True),
                "keep_original_if_failed": self._as_bool(augmentation.get("keep_original_if_failed", True), True),
                "jpeg_quality": self._clamp_int(augmentation.get("jpeg_quality", 95), 95, 1, 100),
                "gray_world": self._as_bool(augmentation.get("gray_world", True), True),
                "clahe": self._as_bool(augmentation.get("clahe", True), True),
                "clahe_clip_limit": self._clamp_float(augmentation.get("clahe_clip_limit", 2.0), 2.0, 0.1),
                "clahe_tile_grid_size": [
                    self._clamp_int(clahe_tile_grid_size[0], 8, 1),
                    self._clamp_int(clahe_tile_grid_size[1], 8, 1),
                ],
                "auto_gamma": self._as_bool(augmentation.get("auto_gamma", False), False),
                "gamma_target_mean": self._clamp_float(augmentation.get("gamma_target_mean", 0.48), 0.48, 0.1, 0.9),
                "denoise": self._as_bool(augmentation.get("denoise", False), False),
                "denoise_h": self._clamp_float(augmentation.get("denoise_h", 3.0), 3.0, 0.0),
                "sharpen": self._as_bool(augmentation.get("sharpen", False), False),
                "sharpen_amount": self._clamp_float(augmentation.get("sharpen_amount", 0.2), 0.2, 0.0, 1.0),
                "max_long_edge": self._clamp_int(augmentation.get("max_long_edge", 0), 0, 0),
            }
        }
        colmap_yaml = {
            "colmap": {
                "scene_name": scene_name,
                "image_path": effective_image_path,
                "raw_image_path": effective_image_path,
                "workspace_path": processed_scene_path,
                "processed_scene_path": processed_scene_path,
                "source_path": source_path,
                "colmap_executable": scene.get("colmap_executable", "colmap"),
                "use_gpu": self._as_bool(scene.get("colmap_use_gpu", True), True),
                "quiet": quiet,
            }
        }

        convert_yaml = {
            "convert": {
                "scene_name": scene_name,
                "source_images": effective_image_path,
                "raw_source_images": raw_image_path,
                "augmented_source_images": augmented_image_path,
                "colmap_workspace": processed_scene_path,
                "gs_input_path": source_path,
                "colmap_executable": scene.get("colmap_executable", ""),
                "magick_executable": scene.get("magick_executable", ""),
                "skip_matching": True,
                "resize": False,
                "use_magick": bool(scene.get("magick_executable", "")),
                "gs_repo": system_paths.get("gs_repo", "third_party/gaussian-splatting"),
                "quiet": quiet,
            }
        }

        viewer_yaml = {
            "viewer": {
                "scene_name": scene_name,
                "source_path": source_path,
                "model_path": output_dir,
                "viewer_root": scene.get("viewer_root", "third_party/viewer/bin"),
                "quiet": quiet,
            }
        }

        video_yaml = {
            "video": {
                "scene_name": scene_name,
                "video_path": video_path,
                "output_images": raw_image_path,
                "ffmpeg_executable": scene.get("ffmpeg_executable", "ffmpeg"),
                "target_fps": self._clamp_int(scene.get("video_target_fps", 2), 2, 1),
                "quiet": quiet,
            }
        }

        self._write_yaml(Path(files["system"]), system_yaml)
        self._write_yaml(Path(files["pipeline"]), pipeline_yaml)
        self._write_yaml(Path(files["train"]), train_yaml)
        self._write_yaml(Path(files["render"]), render_yaml)
        self._write_yaml(Path(files["metrics"]), metrics_yaml)
        self._write_yaml(Path(files["report"]), report_yaml)
        self._write_yaml(Path(files["preflight"]), preflight_yaml)
        self._write_yaml(Path(files["augmentation"]), augmentation_yaml)
        self._write_yaml(Path(files["colmap"]), colmap_yaml)
        self._write_yaml(Path(files["convert"]), convert_yaml)
        self._write_yaml(Path(files["viewer"]), viewer_yaml)
        self._write_yaml(Path(files["video"]), video_yaml)

        return files


runtime_config_service = RuntimeConfigService()
