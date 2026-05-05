from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.app.services.task_service import task_service

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENGINE_ROOT = PROJECT_ROOT / "engine"
BACKEND_RUNTIME_ROOT = PROJECT_ROOT / "backend" / "runtime"


def _task_to_dict(task: Any) -> Dict[str, Any]:
    if task is None:
        return {}

    if hasattr(task, "model_dump"):
        return task.model_dump()

    if hasattr(task, "dict"):
        return task.dict()

    if isinstance(task, dict):
        return task

    return {}


def _safe_read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists() or not path.is_file():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception:
        return {}


def _safe_read_yaml(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists() or not path.is_file():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return data if isinstance(data, dict) else {}

    except Exception:
        return {}


def _resolve_engine_path(value: Optional[Any]) -> Optional[Path]:
    if value is None or value == "":
        return None

    path = Path(str(value))

    if path.is_absolute():
        return path.resolve()

    return (ENGINE_ROOT / path).resolve()


def _resolve_project_path(value: Optional[Any]) -> Optional[Path]:
    if value is None or value == "":
        return None

    path = Path(str(value))

    if path.is_absolute():
        return path.resolve()

    return (PROJECT_ROOT / path).resolve()


def _resolve_existing_file(value: Optional[Any]) -> Optional[Path]:
    path = _resolve_engine_path(value)

    if path and path.exists() and path.is_file():
        return path

    path = _resolve_project_path(value)

    if path and path.exists() and path.is_file():
        return path

    return None


def _existing_str(path: Optional[Path]) -> str:
    if path and path.exists():
        return str(path)

    return ""


def _find_file(base_dir: Optional[Path], filename: str) -> Optional[Path]:
    if not base_dir or not base_dir.exists() or not base_dir.is_dir():
        return None

    direct = base_dir / filename

    if direct.exists() and direct.is_file():
        return direct

    try:
        for path in base_dir.rglob(filename):
            if path.is_file():
                return path

    except Exception:
        return None

    return None


def _first_found(filename: str, *base_dirs: Optional[Path]) -> Optional[Path]:
    for base_dir in base_dirs:
        found = _find_file(base_dir, filename)

        if found:
            return found

    return None


def _find_preview_images(*base_dirs: Optional[Path]) -> List[str]:
    candidates: List[Path] = []

    for base_dir in base_dirs:
        if not base_dir or not base_dir.exists() or not base_dir.is_dir():
            continue

        preferred_dirs = [
            base_dir / "test",
            base_dir / "train",
            base_dir / "renders",
            base_dir / "render",
            base_dir / "preview",
            base_dir / "previews",
        ]

        current_candidates: List[Path] = []

        for directory in preferred_dirs:
            if directory.exists() and directory.is_dir():
                for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                    current_candidates.extend(sorted(directory.rglob(ext)))

        if not current_candidates:
            try:
                for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                    current_candidates.extend(sorted(base_dir.rglob(ext)))

            except Exception:
                current_candidates = []

        candidates.extend(current_candidates)

    seen = set()
    result: List[str] = []

    for path in candidates:
        text = str(path)

        if text not in seen:
            seen.add(text)
            result.append(text)

        if len(result) >= 8:
            break

    return result


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value

    return None


def _pick_value(*sources: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue

        for key in keys:
            if key in source and source[key] not in (None, ""):
                return source[key]

        for nested_key in ("metrics_summary", "metrics", "summary", "result"):
            nested = source.get(nested_key)

            if isinstance(nested, dict):
                for key in keys:
                    if key in nested and nested[key] not in (None, ""):
                        return nested[key]

    return None


def _infer_from_runtime(task_id: str) -> Dict[str, Any]:
    runtime_dir = (BACKEND_RUNTIME_ROOT / task_id).resolve()

    if not runtime_dir.exists():
        return {}

    train_yaml = _safe_read_yaml(runtime_dir / "train.yaml")
    report_yaml = _safe_read_yaml(runtime_dir / "report.yaml")
    metrics_yaml = _safe_read_yaml(runtime_dir / "metrics.yaml")
    colmap_yaml = _safe_read_yaml(runtime_dir / "colmap.yaml")

    train_cfg = train_yaml.get("train", {})
    report_cfg = report_yaml.get("report", {})
    metrics_cfg = metrics_yaml.get("metrics", {})
    colmap_cfg = colmap_yaml.get("colmap", {})

    scene_name = (
        train_cfg.get("scene_name")
        or report_cfg.get("scene_name")
        or metrics_cfg.get("scene_name")
        or task_id
    )

    model_paths = report_cfg.get("model_paths") or metrics_cfg.get("model_paths") or []
    first_model_path = model_paths[0] if model_paths else None

    output_dir = _resolve_engine_path(train_cfg.get("model_output") or first_model_path)
    report_dir = _resolve_engine_path(report_cfg.get("report_dir") or first_model_path)
    log_dir = _resolve_engine_path(report_cfg.get("log_dir") or metrics_cfg.get("log_dir"))
    processed_dir = _resolve_engine_path(
        report_cfg.get("processed_scene_path") or metrics_cfg.get("processed_scene_path")
    )
    source_dir = _resolve_engine_path(train_cfg.get("source_path"))
    raw_image_dir = _resolve_engine_path(
        colmap_cfg.get("raw_image_path") or colmap_cfg.get("image_path")
    )

    return {
        "runtime_dir": runtime_dir,
        "scene_name": scene_name,
        "output_dir": output_dir,
        "report_dir": report_dir,
        "log_dir": log_dir,
        "processed_dir": processed_dir,
        "source_dir": source_dir,
        "raw_image_dir": raw_image_dir,
    }


def _artifact_url(task_id: str, path: str) -> str:
    return "/api/results/{0}/file?path={1}".format(task_id, quote(path, safe=""))


def _artifact_items(task_id: str, paths: List[str], name_map: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    seen = set()

    for raw_path in paths:
        if not raw_path:
            continue

        text = str(raw_path)

        if text in seen:
            continue

        seen.add(text)
        label = name_map.get(text, "") if name_map else ""

        items.append(
            {
                "name": label or Path(text).name or text,
                "path": text,
                "url": _artifact_url(task_id, text),
            }
        )

    return items


def _build_context(task_id: str) -> Dict[str, Any]:
    task = task_service.get_task(task_id)
    task_data = _task_to_dict(task)
    runtime_meta = _infer_from_runtime(task_id)

    if not task_data and not runtime_meta:
        raise HTTPException(status_code=404, detail="任务不存在，且未找到运行时目录")

    stored_result = task_data.get("result", {}) or {}
    stored_metrics = task_data.get("metrics_summary", {}) or {}
    stored_files = task_data.get("result_files", {}) or {}

    scene_name = task_data.get("scene_name") or stored_result.get("scene_name") or runtime_meta.get("scene_name") or task_id

    output_dir = _resolve_engine_path(stored_result.get("output_dir")) or runtime_meta.get("output_dir")
    report_dir = (
        _resolve_engine_path(stored_result.get("report_dir"))
        or runtime_meta.get("report_dir")
        or output_dir
    )
    processed_dir = _resolve_engine_path(stored_result.get("processed_dir")) or runtime_meta.get("processed_dir")
    source_dir = _resolve_engine_path(stored_result.get("source_dir")) or runtime_meta.get("source_dir")
    raw_image_dir = _resolve_engine_path(stored_result.get("raw_image_dir")) or runtime_meta.get("raw_image_dir")
    runtime_dir = _resolve_project_path(stored_result.get("runtime_dir")) or runtime_meta.get("runtime_dir")
    log_dir = (
        _resolve_engine_path(stored_result.get("log_dir"))
        or runtime_meta.get("log_dir")
        or (ENGINE_ROOT / "logs" / scene_name).resolve()
    )

    search_dirs = [report_dir, output_dir, processed_dir, log_dir]

    metrics_json = _resolve_existing_file(stored_files.get("metrics_json")) or _first_found(
        "metrics.json", report_dir, output_dir
    )
    report_json = _resolve_existing_file(stored_files.get("report_json")) or _first_found(
        "report.json", report_dir, output_dir
    )
    report_md = _resolve_existing_file(stored_files.get("report_md")) or _first_found(
        "report.md", report_dir, output_dir
    )
    summary_csv = _resolve_existing_file(stored_files.get("summary_csv")) or _first_found(
        "summary.csv", report_dir, output_dir
    )
    summary_txt = _resolve_existing_file(stored_files.get("summary_txt")) or _first_found(
        "summary.txt", report_dir, output_dir
    )
    colmap_quality_json = _resolve_existing_file(
        stored_files.get("colmap_quality_json")
    ) or _first_found("colmap_quality.json", *search_dirs)
    colmap_quality_txt = _resolve_existing_file(
        stored_files.get("colmap_quality_txt")
    ) or _first_found("colmap_quality.txt", *search_dirs)

    metrics_data = _safe_read_json(metrics_json)
    report_data = _safe_read_json(report_json)
    colmap_quality_data = _safe_read_json(colmap_quality_json)

    result_files = {
        "metrics_json": _existing_str(metrics_json),
        "report_json": _existing_str(report_json),
        "report_md": _existing_str(report_md),
        "summary_csv": _existing_str(summary_csv),
        "summary_txt": _existing_str(summary_txt),
        "colmap_quality_json": _existing_str(colmap_quality_json),
        "colmap_quality_txt": _existing_str(colmap_quality_txt),
    }

    metrics_summary = {
        "psnr": _first_nonempty(
            stored_metrics.get("psnr"),
            _pick_value(metrics_data, report_data, stored_result, keys=("psnr", "PSNR")),
        ),
        "ssim": _first_nonempty(
            stored_metrics.get("ssim"),
            _pick_value(metrics_data, report_data, stored_result, keys=("ssim", "SSIM")),
        ),
        "lpips": _first_nonempty(
            stored_metrics.get("lpips"),
            _pick_value(metrics_data, report_data, stored_result, keys=("lpips", "LPIPS")),
        ),
        "mse": _first_nonempty(
            stored_metrics.get("mse"),
            _pick_value(metrics_data, report_data, stored_result, keys=("mse", "MSE")),
        ),
        "mae": _first_nonempty(
            stored_metrics.get("mae"),
            _pick_value(metrics_data, report_data, stored_result, keys=("mae", "MAE")),
        ),
        "gaussian_count": _first_nonempty(
            stored_metrics.get("gaussian_count"),
            _pick_value(metrics_data, report_data, stored_result, keys=("gaussian_count", "num_gaussians")),
        ),
        "latest_iteration": _first_nonempty(
            stored_metrics.get("latest_iteration"),
            _pick_value(metrics_data, report_data, stored_result, keys=("latest_iteration", "iteration")),
        ),
        "generated_at": _first_nonempty(
            stored_metrics.get("generated_at"),
            _pick_value(metrics_data, report_data, stored_result, keys=("generated_at", "created_at")),
        ),
        "colmap_registration_rate": colmap_quality_data.get("registration_rate_percent"),
        "colmap_registered_images": colmap_quality_data.get("registered_image_count"),
        "colmap_input_images": colmap_quality_data.get("input_image_count"),
        "colmap_point3d_count": colmap_quality_data.get("point3d_count"),
        "colmap_camera_count": colmap_quality_data.get("camera_count"),
        "colmap_mean_track_length": colmap_quality_data.get("mean_track_length"),
        "colmap_mean_reprojection_error": colmap_quality_data.get("mean_reprojection_error"),
        "colmap_quality_level": colmap_quality_data.get("quality_level"),
    }

    metrics_summary = {
        key: value for key, value in metrics_summary.items() if value is not None and value != ""
    }

    report_summary = report_data or stored_result.get("report_summary", {}) or {}

    preview_images_raw = stored_result.get("preview_images") or report_summary.get("preview_images") or _find_preview_images(
        report_dir,
        output_dir,
    )
    preview_images = [str(item) for item in preview_images_raw if item]

    file_name_map = {
        value: key
        for key, value in result_files.items()
        if value
    }
    artifact_paths = [value for value in result_files.values() if value]
    artifacts = _artifact_items(task_id, artifact_paths, file_name_map)
    images = _artifact_items(task_id, preview_images)

    result_payload = {
        "output_dir": str(output_dir) if output_dir else None,
        "report_dir": str(report_dir) if report_dir else None,
        "log_dir": str(log_dir) if log_dir else None,
        "processed_dir": str(processed_dir) if processed_dir else None,
        "runtime_dir": str(runtime_dir) if runtime_dir else None,
        "source_dir": str(source_dir) if source_dir else None,
        "raw_image_dir": str(raw_image_dir) if raw_image_dir else None,
        "preview_images": images,
        "preview_image_paths": preview_images,
        "artifacts": artifacts,
        "result_files": result_files,
        "report_summary": report_summary,
        "colmap_quality": colmap_quality_data or stored_result.get("colmap_quality", {}),
    }

    inferred_status = (
        "success"
        if any(value for value in result_files.values())
        else (task_data.get("status") or "unknown")
    )

    return {
        "task_data": task_data,
        "runtime_meta": runtime_meta,
        "paths": {
            "output_dir": output_dir,
            "report_dir": report_dir,
            "processed_dir": processed_dir,
            "source_dir": source_dir,
            "raw_image_dir": raw_image_dir,
            "runtime_dir": runtime_dir,
            "log_dir": log_dir,
        },
        "response": {
            "task_id": task_data.get("task_id", task_id),
            "scene_name": scene_name,
            "status": inferred_status,
            "current_stage": task_data.get("current_stage", "结果查看"),
            "retry_count": task_data.get("retry_count", 0),
            "stop_requested": task_data.get("stop_requested", False),
            "force_stop_requested": task_data.get("force_stop_requested", False),
            "message": task_data.get("message", "结果已从磁盘恢复"),
            "error": task_data.get("error"),
            "created_at": task_data.get("created_at"),
            "started_at": task_data.get("started_at"),
            "finished_at": task_data.get("finished_at"),
            "stage_history": task_data.get("stage_history", []),
            "metrics_summary": metrics_summary,
            "metrics": metrics_summary,
            "result_files": result_files,
            "artifacts": artifacts,
            "files": artifacts,
            "images": images,
            "report": report_summary,
            "report_json": report_summary,
            "report_summary": report_summary,
            "report_url": "/api/results/{0}/report".format(task_id) if report_summary else "",
            "result": result_payload,
        },
    }


def _is_inside(path: Path, root: Optional[Path]) -> bool:
    if root is None:
        return False

    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


@router.get("/{task_id}")
def get_result(task_id: str):
    return _build_context(task_id)["response"]


@router.get("/{task_id}/report")
def get_report(task_id: str):
    response = _build_context(task_id)["response"]
    report = response.get("report_summary") or response.get("report")

    if not report:
        raise HTTPException(status_code=404, detail="未找到 report.json")

    return report


@router.get("/{task_id}/report.json")
def get_report_json(task_id: str):
    return get_report(task_id)


@router.get("/{task_id}/file")
def get_result_file(task_id: str, path: str = Query(..., description="结果文件绝对路径或 engine 相对路径")):
    context = _build_context(task_id)
    candidate = _resolve_engine_path(path) or _resolve_project_path(path)

    if candidate is None or not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    allowed_roots: List[Optional[Path]] = [
        PROJECT_ROOT,
        ENGINE_ROOT,
        BACKEND_RUNTIME_ROOT,
        *context.get("paths", {}).values(),
    ]

    if not any(_is_inside(candidate, root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="不允许访问该文件路径")

    return FileResponse(str(candidate), filename=candidate.name)
