from pathlib import Path
import subprocess
import sys
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger


class MetricsService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        metrics_config_path="configs/metrics.yaml"
    ):
        self.pm = PathManager(system_config_path)

        metrics_config_path = Path(metrics_config_path)
        if not metrics_config_path.is_absolute():
            metrics_config_path = self.pm.project_root / metrics_config_path

        self.metrics_cfg = load_yaml(str(metrics_config_path))["metrics"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _find_latest_iteration_dir(self, model_path: Path) -> Tuple[Optional[int], Optional[Path]]:
        point_cloud_dir = model_path / "point_cloud"
        if not point_cloud_dir.exists():
            return None, None

        iteration_dirs = []
        for item in point_cloud_dir.iterdir():
            if item.is_dir() and item.name.startswith("iteration_"):
                match = re.search(r"iteration_(\d+)", item.name)
                if match:
                    iteration_dirs.append((int(match.group(1)), item))

        if not iteration_dirs:
            return None, None

        iteration_dirs.sort(key=lambda x: x[0])
        return iteration_dirs[-1]

    def _count_gaussians_from_ply(self, ply_path: Path) -> Optional[int]:
        if not ply_path.exists():
            return None

        try:
            with open(ply_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("element vertex"):
                        parts = line.split()
                        if len(parts) == 3:
                            return int(parts[2])
                    if line == "end_header":
                        break
        except Exception:
            return None

        return None

    def _collect_preview_images(self, model_path: Path) -> List[str]:
        candidates = []

        for folder_name in ["test", "train", "renders", "render", "images"]:
            folder = model_path / folder_name
            if folder.exists():
                for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                    candidates.extend(folder.rglob(pattern))

        if not candidates:
            for pattern in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                candidates.extend(model_path.rglob(pattern))

        candidates = sorted(set(candidates))[:6]
        return [str(p) for p in candidates]

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except Exception:
            return None

    def _extract_metrics_from_json(self, data: Dict[str, Any]) -> Dict[str, Optional[float]]:
        result = {
            "psnr": None,
            "ssim": None,
            "lpips": None,
            "mse": None,
            "mae": None,
        }

        def try_extract(d: Dict[str, Any]) -> Dict[str, Optional[float]]:
            local = {
                "psnr": None,
                "ssim": None,
                "lpips": None,
                "mse": None,
                "mae": None,
            }

            for key, value in d.items():
                if not isinstance(key, str):
                    continue

                key_lower = key.lower()
                if isinstance(value, (int, float)):
                    if "psnr" in key_lower:
                        local["psnr"] = float(value)
                    elif "ssim" in key_lower:
                        local["ssim"] = float(value)
                    elif "lpips" in key_lower:
                        local["lpips"] = float(value)
                    elif key_lower == "mse" or "mse" in key_lower:
                        local["mse"] = float(value)
                    elif key_lower == "mae" or "mae" in key_lower:
                        local["mae"] = float(value)

            return local

        top = try_extract(data)
        if any(v is not None for v in top.values()):
            return top

        for _, value in data.items():
            if isinstance(value, dict):
                nested = try_extract(value)
                if any(v is not None for v in nested.values()):
                    return nested

        return result

    def _find_existing_metrics_file(self, model_path: Path) -> Optional[Path]:
        candidates = [
            model_path / "results.json",
            model_path / "eval_results.json",
            model_path / "metrics_result.json",
        ]

        for path in candidates:
            if path.exists():
                return path

        json_files = list(model_path.glob("*.json"))
        for path in json_files:
            if path.name == "metrics.json":
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                metrics = self._extract_metrics_from_json(data)
                if any(v is not None for v in metrics.values()):
                    return path
            except Exception:
                continue

        return None

    def _extract_metrics_from_output_lines(self, lines: List[str]) -> Dict[str, Optional[float]]:
        result = {
            "psnr": None,
            "ssim": None,
            "lpips": None,
            "mse": None,
            "mae": None,
        }

        patterns = {
            "psnr": re.compile(r"psnr[^0-9\-]*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
            "ssim": re.compile(r"ssim[^0-9\-]*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
            "lpips": re.compile(r"lpips[^0-9\-]*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
            "mse": re.compile(r"mse[^0-9\-]*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
            "mae": re.compile(r"mae[^0-9\-]*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE),
        }

        for line in lines:
            for key, pattern in patterns.items():
                match = pattern.search(line)
                if match:
                    result[key] = self._safe_float(match.group(1))

        return result

    def _build_metrics_summary(
        self,
        scene_name: str,
        model_path: Path,
        output_lines: List[str],
    ) -> Dict[str, Any]:
        latest_iteration, latest_dir = self._find_latest_iteration_dir(model_path)

        gaussian_count = None
        if latest_dir is not None:
            ply_path = latest_dir / "point_cloud.ply"
            gaussian_count = self._count_gaussians_from_ply(ply_path)

        preview_images = self._collect_preview_images(model_path)

        metrics = self._extract_metrics_from_output_lines(output_lines)

        existing_metrics_file = self._find_existing_metrics_file(model_path)
        metrics_source_file = ""
        if existing_metrics_file is not None:
            try:
                with open(existing_metrics_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                from_json = self._extract_metrics_from_json(data)
                for key, value in from_json.items():
                    if value is not None:
                        metrics[key] = value
                metrics_source_file = str(existing_metrics_file)
            except Exception:
                metrics_source_file = ""

        return {
            "scene_name": scene_name,
            "model_path": str(model_path),
            "psnr": metrics.get("psnr"),
            "ssim": metrics.get("ssim"),
            "lpips": metrics.get("lpips"),
            "mse": metrics.get("mse"),
            "mae": metrics.get("mae"),
            "gaussian_count": gaussian_count,
            "latest_iteration": latest_iteration,
            "preview_images": preview_images,
            "metrics_source_file": metrics_source_file,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _write_metrics_json(self, model_path: Path, summary: Dict[str, Any]) -> Path:
        metrics_json = model_path / "metrics.json"
        with open(metrics_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return metrics_json

    def run(self):
        scene_name = self.metrics_cfg["scene_name"]
        model_paths = self.metrics_cfg.get("model_paths", [])
        quiet = self.metrics_cfg.get("quiet", False)

        if not model_paths:
            raise ValueError("metrics.yaml 中 model_paths 不能为空")

        resolved_model_paths = [self._resolve_user_path(p) for p in model_paths]

        for p in resolved_model_paths:
            if not p.exists():
                raise FileNotFoundError("模型目录不存在: {0}".format(p))

        metrics_script = (self.pm.gs_repo / "metrics.py").resolve()
        if not metrics_script.exists():
            raise FileNotFoundError("官方 metrics.py 不存在: {0}".format(metrics_script))

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "metrics.log"
        logger = setup_logger(str(log_file))

        cmd = [
            sys.executable,
            str(metrics_script),
            "-m",
        ]
        cmd.extend([str(p) for p in resolved_model_paths])

        if quiet:
            cmd.append("--quiet")

        logger.info("开始评测")
        logger.info("项目根目录: %s", self.pm.project_root)
        logger.info("3DGS仓库目录: %s", self.pm.gs_repo)
        logger.info("场景名称: %s", scene_name)
        logger.info("模型目录列表: %s", ", ".join([str(p) for p in resolved_model_paths]))
        logger.info("执行命令: %s", " ".join(cmd))

        print("开始评测: {0}".format(scene_name))
        for p in resolved_model_paths:
            print("模型目录: {0}".format(p))

        process = subprocess.Popen(
            cmd,
            cwd=str(self.pm.gs_repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        output_lines = []
        for line in process.stdout:
            line = line.rstrip()
            output_lines.append(line)
            print(line)
            logger.info(line)

        process.wait()

        if process.returncode != 0:
            logger.error("评测失败，返回码: %s", process.returncode)
            raise RuntimeError("评测失败，返回码: {0}".format(process.returncode))

        logger.info("评测完成")
        print("评测完成")

        for model_path in resolved_model_paths:
            summary = self._build_metrics_summary(
                scene_name=scene_name,
                model_path=model_path,
                output_lines=output_lines,
            )
            metrics_json = self._write_metrics_json(model_path, summary)
            logger.info("已写入指标文件: %s", metrics_json)
            print("已写入指标文件: {0}".format(metrics_json))