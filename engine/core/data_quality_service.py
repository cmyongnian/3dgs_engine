from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from engine.core.config import load_yaml
from engine.core.logger import setup_logger
from engine.core.paths import PathManager
from engine.core.process_utils import raise_if_force_stopped


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


@dataclass
class ImageQualityItem:
    filename: str
    status: str
    width: int = 0
    height: int = 0
    blur_score: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    dark_pixel_ratio: float = 0.0
    overexposed_pixel_ratio: float = 0.0
    duplicate_like: bool = False
    warnings: List[str] = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


class DataQualityService:
    """输入数据质量体检与预处理诊断模块。

    该模块不会改变原始图像，只在任务开始阶段扫描输入图片目录，生成
    data_quality_report.json / data_quality_report.txt。报告用于判断图片数量、
    分辨率一致性、模糊、曝光异常、疑似重复帧等风险，并给出预处理建议。
    """

    def __init__(
        self,
        system_config_path: str = "configs/system.yaml",
        data_quality_config_path: str = "configs/data_quality.yaml",
        task_id: Optional[str] = None,
    ) -> None:
        self.pm = PathManager(system_config_path)
        self.task_id = task_id or ""

        config_path = Path(data_quality_config_path)
        if not config_path.is_absolute():
            config_path = self.pm.project_root / config_path

        loaded = load_yaml(str(config_path))
        self.cfg = loaded.get("data_quality", loaded if isinstance(loaded, dict) else {})

    def _resolve_user_path(self, value: Optional[str]) -> Optional[Path]:
        if not value:
            return None
        path = Path(str(value))
        if path.is_absolute():
            return path.resolve()
        return (self.pm.project_root / path).resolve()

    def _iter_images(self, image_dir: Path) -> List[Path]:
        if not image_dir.exists() or not image_dir.is_dir():
            return []
        return sorted(
            path for path in image_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS
        )

    def _sample_images(self, images: Sequence[Path], max_items: int) -> List[Path]:
        if max_items <= 0 or len(images) <= max_items:
            return list(images)
        if max_items == 1:
            return [images[0]]
        indexes = np.linspace(0, len(images) - 1, max_items).round().astype(int).tolist()
        result: List[Path] = []
        seen = set()
        for index in indexes:
            if index not in seen:
                seen.add(index)
                result.append(images[index])
        return result

    def _read_image_gray(self, path: Path) -> Tuple[np.ndarray, Tuple[int, int]]:
        # 使用 np.fromfile + cv2.imdecode，兼容 Windows 中文路径。
        data = np.fromfile(str(path), dtype=np.uint8)
        image_bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise RuntimeError("OpenCV 无法读取图片")
        height, width = image_bgr.shape[:2]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        return gray, (width, height)

    def _average_hash(self, gray: np.ndarray) -> np.ndarray:
        small = cv2.resize(gray, (8, 8), interpolation=cv2.INTER_AREA)
        return small >= float(small.mean())

    @staticmethod
    def _hash_distance(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> int:
        if a is None or b is None:
            return 64
        return int(np.count_nonzero(a != b))

    def _analyse_one(
        self,
        image_path: Path,
        previous_hash: Optional[np.ndarray],
        duplicate_hamming_threshold: int,
        blur_threshold: float,
        severe_blur_threshold: float,
        dark_mean_threshold: float,
        bright_mean_threshold: float,
        dark_pixel_ratio_threshold: float,
        overexposed_pixel_ratio_threshold: float,
        low_contrast_threshold: float,
    ) -> Tuple[ImageQualityItem, Optional[np.ndarray]]:
        try:
            gray, (width, height) = self._read_image_gray(image_path)
            gray_f = gray.astype(np.float32) / 255.0

            blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            brightness = float(gray_f.mean())
            contrast = float(gray_f.std())
            dark_pixel_ratio = float((gray < 30).mean())
            overexposed_pixel_ratio = float((gray > 245).mean())
            current_hash = self._average_hash(gray)
            duplicate_like = self._hash_distance(previous_hash, current_hash) <= duplicate_hamming_threshold

            warnings: List[str] = []
            if blur_score < severe_blur_threshold:
                warnings.append("严重模糊")
            elif blur_score < blur_threshold:
                warnings.append("轻微模糊")

            if brightness < dark_mean_threshold or dark_pixel_ratio > dark_pixel_ratio_threshold:
                warnings.append("偏暗或暗部占比过高")
            if brightness > bright_mean_threshold or overexposed_pixel_ratio > overexposed_pixel_ratio_threshold:
                warnings.append("偏亮或过曝区域较多")
            if contrast < low_contrast_threshold:
                warnings.append("对比度偏低")
            if duplicate_like:
                warnings.append("疑似重复帧")

            return (
                ImageQualityItem(
                    filename=image_path.name,
                    status="ok",
                    width=width,
                    height=height,
                    blur_score=round(blur_score, 4),
                    brightness=round(brightness, 4),
                    contrast=round(contrast, 4),
                    dark_pixel_ratio=round(dark_pixel_ratio, 4),
                    overexposed_pixel_ratio=round(overexposed_pixel_ratio, 4),
                    duplicate_like=duplicate_like,
                    warnings=warnings,
                ),
                current_hash,
            )
        except Exception as exc:
            return (
                ImageQualityItem(
                    filename=image_path.name,
                    status="unreadable",
                    warnings=["不可读取"],
                    message=str(exc),
                ),
                previous_hash,
            )

    @staticmethod
    def _safe_avg(values: Iterable[float]) -> float:
        vals = [float(item) for item in values if item is not None]
        if not vals:
            return 0.0
        return float(sum(vals) / len(vals))

    @staticmethod
    def _safe_std(values: Iterable[float]) -> float:
        vals = [float(item) for item in values if item is not None]
        if len(vals) < 2:
            return 0.0
        return float(np.std(np.array(vals, dtype=np.float32)))

    def _score_and_risk(self, summary: Dict[str, Any]) -> Tuple[int, str, str, str]:
        total = int(summary.get("total_images", 0) or 0)
        unreadable = int(summary.get("unreadable_images", 0) or 0)
        blur = int(summary.get("blur_images", 0) or 0)
        severe_blur = int(summary.get("severe_blur_images", 0) or 0)
        dark = int(summary.get("dark_images", 0) or 0)
        overexposed = int(summary.get("overexposed_images", 0) or 0)
        low_contrast = int(summary.get("low_contrast_images", 0) or 0)
        duplicates = int(summary.get("duplicate_like_images", 0) or 0)
        inconsistent_resolution = not bool(summary.get("resolution_consistency", True))

        score = 100

        if total <= 0:
            score = 0
        elif total < 20:
            score -= 30
        elif total < 50:
            score -= 12

        if total > 0:
            score -= min(25, round((unreadable / total) * 80))
            score -= min(18, round((blur / total) * 35))
            score -= min(18, round((severe_blur / total) * 60))
            score -= min(12, round(((dark + overexposed) / total) * 25))
            score -= min(8, round((low_contrast / total) * 20))
            score -= min(10, round((duplicates / total) * 25))

        if inconsistent_resolution:
            score -= 10

        score = int(max(0, min(100, score)))

        if score >= 80:
            return score, "low", "低风险", "pass"
        if score >= 60:
            return score, "medium", "中风险", "warning"
        return score, "high", "高风险", "danger"

    def _build_recommendations(self, summary: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        total = int(summary.get("total_images", 0) or 0)
        blur = int(summary.get("blur_images", 0) or 0)
        severe_blur = int(summary.get("severe_blur_images", 0) or 0)
        dark = int(summary.get("dark_images", 0) or 0)
        overexposed = int(summary.get("overexposed_images", 0) or 0)
        low_contrast = int(summary.get("low_contrast_images", 0) or 0)
        duplicates = int(summary.get("duplicate_like_images", 0) or 0)
        unreadable = int(summary.get("unreadable_images", 0) or 0)
        resolution_consistency = bool(summary.get("resolution_consistency", True))

        conclusions: List[str] = []
        recommendations: List[str] = []

        if total <= 0:
            conclusions.append("未检测到可用于 3DGS / COLMAP 的输入图像。")
            recommendations.append("请检查原始图片目录或视频抽帧输出目录是否填写正确。")
            return conclusions, recommendations

        conclusions.append(
            f"共检测到 {total} 张输入图片，主分辨率为 {summary.get('main_resolution', '未知')}。"
        )

        if total < 20:
            conclusions.append("图片数量偏少，COLMAP 特征匹配和相机位姿估计存在较高失败风险。")
            recommendations.append("建议补充采集更多视角，尽量覆盖场景不同方向和尺度变化。")
        elif total < 50:
            conclusions.append("图片数量基本可用，但对复杂场景仍可能不足。")
            recommendations.append("如场景较大或纹理较弱，建议增加图片数量至 50 张以上。")
        else:
            conclusions.append("图片数量满足常规 3DGS 重建的基本需求。")

        if not resolution_consistency:
            conclusions.append("检测到输入图片分辨率不一致，可能影响特征提取稳定性。")
            recommendations.append("建议统一图像尺寸，或在数据增强中设置 max_long_edge 做等比例缩放。")

        if unreadable > 0:
            conclusions.append(f"存在 {unreadable} 张不可读取图片，需要在训练前清理。")
            recommendations.append("建议删除损坏图片，避免预检查或 COLMAP 阶段中断。")

        if blur > 0:
            conclusions.append(f"检测到 {blur} 张可能模糊图片，其中严重模糊 {severe_blur} 张。")
            recommendations.append("建议删除严重模糊帧；视频数据可降低抽帧 FPS 或重新采集更稳定的镜头。")

        if dark > 0 or overexposed > 0:
            conclusions.append(f"曝光异常图片共 {dark + overexposed} 张，其中偏暗 {dark} 张、过曝 {overexposed} 张。")
            recommendations.append("建议开启 gray_world、CLAHE 或 low_light 预设；若过曝严重，应优先重新采集。")

        if low_contrast > 0:
            conclusions.append(f"检测到 {low_contrast} 张低对比度图片，可能降低 COLMAP 特征匹配数量。")
            recommendations.append("建议开启 CLAHE 局部对比度增强，但避免过强锐化导致噪声放大。")

        if duplicates > 0:
            conclusions.append(f"检测到 {duplicates} 张疑似重复帧，可能说明视频抽帧间隔过密。")
            recommendations.append("如输入来自视频，建议适当降低 target_fps，减少重复帧并保留有视角变化的帧。")

        if not recommendations:
            recommendations.append("当前数据质量风险较低，可继续执行 COLMAP 与 3DGS 训练。")

        return conclusions, recommendations

    def _write_reports(self, report: Dict[str, Any], log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        json_path = log_dir / "data_quality_report.json"
        txt_path = log_dir / "data_quality_report.txt"

        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        summary = report.get("summary", {})
        checks = report.get("checks", {})
        lines = [
            "========== 数据质量体检与预处理诊断报告 ==========" ,
            f"任务 ID: {report.get('task_id', '')}",
            f"场景名称: {report.get('scene_name', '')}",
            f"输入模式: {report.get('input_mode', '')}",
            f"图片目录: {report.get('image_dir', '')}",
            f"生成时间: {report.get('generated_at', '')}",
            "",
            f"综合评分: {report.get('score', 0)} / 100",
            f"风险等级: {report.get('risk_label', '')}",
            "",
            "--- 核心统计 ---",
            f"图片总数: {summary.get('total_images', 0)}",
            f"抽样分析数: {summary.get('sampled_images', 0)}",
            f"可读取图片: {summary.get('readable_images', 0)}",
            f"不可读取图片: {summary.get('unreadable_images', 0)}",
            f"主分辨率: {summary.get('main_resolution', '未知')}",
            f"分辨率一致: {'是' if summary.get('resolution_consistency', True) else '否'}",
            f"平均清晰度: {summary.get('avg_blur_score', 0)}",
            f"模糊图片: {summary.get('blur_images', 0)}",
            f"严重模糊图片: {summary.get('severe_blur_images', 0)}",
            f"平均亮度: {summary.get('avg_brightness', 0)}",
            f"偏暗图片: {summary.get('dark_images', 0)}",
            f"过曝图片: {summary.get('overexposed_images', 0)}",
            f"低对比度图片: {summary.get('low_contrast_images', 0)}",
            f"疑似重复帧: {summary.get('duplicate_like_images', 0)}",
            "",
            "--- 分辨率统计 ---",
        ]

        resolution_counter = summary.get("resolution_counter", {})
        if resolution_counter:
            for key, value in resolution_counter.items():
                lines.append(f"- {key}: {value} 张")
        else:
            lines.append("- 无")

        lines.extend(["", "--- 自动结论 ---"])
        for item in report.get("conclusions", []):
            lines.append(f"- {item}")

        lines.extend(["", "--- 预处理建议 ---"])
        for item in report.get("recommendations", []):
            lines.append(f"- {item}")

        txt_path.write_text("\n".join(lines), encoding="utf-8")

    def run(self) -> None:
        raise_if_force_stopped(self.task_id)

        scene_name = str(self.cfg.get("scene_name") or "default_scene")
        input_mode = str(self.cfg.get("input_mode") or "images")
        image_dir = self._resolve_user_path(
            self.cfg.get("image_dir") or self.cfg.get("raw_image_path") or self.cfg.get("input_images")
        )
        log_dir = self._resolve_user_path(self.cfg.get("log_dir")) or self.pm.scene_log(scene_name)
        video_path = self.cfg.get("video_path", "")

        max_sample_images = int(self.cfg.get("max_sample_images", 300) or 300)
        min_images = int(self.cfg.get("min_images", 20) or 20)
        blur_threshold = float(self.cfg.get("blur_threshold", 100.0) or 100.0)
        severe_blur_threshold = float(self.cfg.get("severe_blur_threshold", 50.0) or 50.0)
        dark_mean_threshold = float(self.cfg.get("dark_mean_threshold", 0.28) or 0.28)
        bright_mean_threshold = float(self.cfg.get("bright_mean_threshold", 0.78) or 0.78)
        dark_pixel_ratio_threshold = float(self.cfg.get("dark_pixel_ratio_threshold", 0.45) or 0.45)
        overexposed_pixel_ratio_threshold = float(self.cfg.get("overexposed_pixel_ratio_threshold", 0.15) or 0.15)
        low_contrast_threshold = float(self.cfg.get("low_contrast_threshold", 0.08) or 0.08)
        duplicate_hamming_threshold = int(self.cfg.get("duplicate_hamming_threshold", 3) or 3)
        fail_on_high_risk = bool(self.cfg.get("fail_on_high_risk", False))

        log_dir.mkdir(parents=True, exist_ok=True)
        logger = setup_logger(str(log_dir / "data_quality.log"))

        print("开始数据质量体检")
        print("场景名称:", scene_name)
        print("输入模式:", input_mode)
        print("图片目录:", image_dir)

        logger.info("开始数据质量体检")
        logger.info("场景名称: %s", scene_name)
        logger.info("输入模式: %s", input_mode)
        logger.info("图片目录: %s", image_dir)

        all_images: List[Path] = []
        missing_message = ""
        if image_dir is None:
            missing_message = "未配置图片目录"
        elif not image_dir.exists():
            missing_message = f"图片目录不存在: {image_dir}"
        elif not image_dir.is_dir():
            missing_message = f"图片路径不是目录: {image_dir}"
        else:
            all_images = self._iter_images(image_dir)

        sampled_images = self._sample_images(all_images, max_sample_images)
        items: List[ImageQualityItem] = []
        previous_hash: Optional[np.ndarray] = None

        if missing_message:
            logger.warning(missing_message)

        for index, image_path in enumerate(sampled_images, start=1):
            raise_if_force_stopped(self.task_id)
            item, previous_hash = self._analyse_one(
                image_path=image_path,
                previous_hash=previous_hash,
                duplicate_hamming_threshold=duplicate_hamming_threshold,
                blur_threshold=blur_threshold,
                severe_blur_threshold=severe_blur_threshold,
                dark_mean_threshold=dark_mean_threshold,
                bright_mean_threshold=bright_mean_threshold,
                dark_pixel_ratio_threshold=dark_pixel_ratio_threshold,
                overexposed_pixel_ratio_threshold=overexposed_pixel_ratio_threshold,
                low_contrast_threshold=low_contrast_threshold,
            )
            items.append(item)
            if index % 50 == 0 or index == len(sampled_images):
                print(f"数据质量体检进度: {index}/{len(sampled_images)}")

        readable_items = [item for item in items if item.status == "ok"]
        resolution_counter = Counter(
            f"{item.width}x{item.height}" for item in readable_items if item.width and item.height
        )
        main_resolution = resolution_counter.most_common(1)[0][0] if resolution_counter else "无"

        blur_images = [item for item in readable_items if item.blur_score < blur_threshold]
        severe_blur_images = [item for item in readable_items if item.blur_score < severe_blur_threshold]
        dark_images = [
            item for item in readable_items
            if item.brightness < dark_mean_threshold or item.dark_pixel_ratio > dark_pixel_ratio_threshold
        ]
        overexposed_images = [
            item for item in readable_items
            if item.brightness > bright_mean_threshold or item.overexposed_pixel_ratio > overexposed_pixel_ratio_threshold
        ]
        low_contrast_images = [item for item in readable_items if item.contrast < low_contrast_threshold]
        duplicate_like_images = [item for item in readable_items if item.duplicate_like]

        summary = {
            "total_images": len(all_images),
            "sampled_images": len(sampled_images),
            "readable_images": len(readable_items),
            "unreadable_images": len(items) - len(readable_items),
            "main_resolution": main_resolution,
            "resolution_counter": dict(resolution_counter),
            "resolution_consistency": len(resolution_counter) <= 1,
            "avg_blur_score": round(self._safe_avg(item.blur_score for item in readable_items), 4),
            "min_blur_score": round(min((item.blur_score for item in readable_items), default=0.0), 4),
            "blur_images": len(blur_images),
            "severe_blur_images": len(severe_blur_images),
            "avg_brightness": round(self._safe_avg(item.brightness for item in readable_items), 4),
            "brightness_std": round(self._safe_std(item.brightness for item in readable_items), 4),
            "dark_images": len(dark_images),
            "overexposed_images": len(overexposed_images),
            "avg_contrast": round(self._safe_avg(item.contrast for item in readable_items), 4),
            "low_contrast_images": len(low_contrast_images),
            "duplicate_like_images": len(duplicate_like_images),
            "sampling_note": (
                f"输入图片较多，仅均匀抽样分析 {len(sampled_images)} 张。"
                if len(sampled_images) < len(all_images) else "已分析全部输入图片。"
            ),
        }

        score, risk_level, risk_label, status = self._score_and_risk(summary)
        conclusions, recommendations = self._build_recommendations(summary)

        checks = {
            "image_count": {
                "status": "pass" if len(all_images) >= min_images else "warning",
                "value": len(all_images),
                "threshold": min_images,
            },
            "resolution": {
                "status": "pass" if summary["resolution_consistency"] else "warning",
                "main_resolution": main_resolution,
                "resolution_counter": dict(resolution_counter),
            },
            "blur": {
                "status": "pass" if not blur_images else "warning",
                "threshold": blur_threshold,
                "severe_threshold": severe_blur_threshold,
                "blur_images": len(blur_images),
                "severe_blur_images": len(severe_blur_images),
            },
            "exposure": {
                "status": "pass" if not dark_images and not overexposed_images else "warning",
                "dark_images": len(dark_images),
                "overexposed_images": len(overexposed_images),
                "dark_mean_threshold": dark_mean_threshold,
                "bright_mean_threshold": bright_mean_threshold,
            },
            "contrast": {
                "status": "pass" if not low_contrast_images else "warning",
                "low_contrast_images": len(low_contrast_images),
                "low_contrast_threshold": low_contrast_threshold,
            },
            "duplicate": {
                "status": "pass" if not duplicate_like_images else "warning",
                "duplicate_like_images": len(duplicate_like_images),
                "hamming_threshold": duplicate_hamming_threshold,
            },
        }

        suspicious = [
            asdict(item) for item in items
            if item.status != "ok" or item.warnings
        ][:80]

        report = {
            "task_id": self.task_id,
            "scene_name": scene_name,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "input_mode": input_mode,
            "image_dir": str(image_dir) if image_dir else "",
            "video_path": str(video_path or ""),
            "score": score,
            "risk_level": risk_level,
            "risk_label": risk_label,
            "status": status,
            "summary": summary,
            "checks": checks,
            "conclusions": conclusions,
            "recommendations": recommendations,
            "thresholds": {
                "min_images": min_images,
                "max_sample_images": max_sample_images,
                "blur_threshold": blur_threshold,
                "severe_blur_threshold": severe_blur_threshold,
                "dark_mean_threshold": dark_mean_threshold,
                "bright_mean_threshold": bright_mean_threshold,
                "dark_pixel_ratio_threshold": dark_pixel_ratio_threshold,
                "overexposed_pixel_ratio_threshold": overexposed_pixel_ratio_threshold,
                "low_contrast_threshold": low_contrast_threshold,
                "duplicate_hamming_threshold": duplicate_hamming_threshold,
            },
            "suspicious_items": suspicious,
            "notes": "该模块只进行质量诊断，不修改原始图片；预处理建议可用于选择数据增强预设或重新采集数据。",
        }

        self._write_reports(report, log_dir)

        print(f"数据质量体检完成：评分 {score}/100，风险等级 {risk_label}。")
        print("报告已保存到:", log_dir / "data_quality_report.json")
        logger.info("数据质量体检完成：评分 %s/100，风险等级 %s", score, risk_label)

        if fail_on_high_risk and risk_level == "high":
            raise RuntimeError("数据质量体检判定为高风险，已根据配置终止任务。")
