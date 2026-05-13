from pathlib import Path
from collections import Counter

from PIL import Image, UnidentifiedImageError
import cv2
import numpy as np

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger


class PreflightService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        preflight_config_path="configs/preflight.yaml",
    ):
        self.pm = PathManager(system_config_path)

        preflight_config_path = Path(preflight_config_path)
        if not preflight_config_path.is_absolute():
            preflight_config_path = self.pm.project_root / preflight_config_path

        self.preflight_cfg = load_yaml(str(preflight_config_path))["preflight"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _collect_images(self, image_path: Path):
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

        if not image_path.exists() or not image_path.is_dir():
            return []

        images = [
            p for p in image_path.iterdir()
            if p.is_file() and p.suffix.lower() in image_exts
        ]

        return sorted(images, key=lambda x: x.name)

    def _read_image_gray(self, image_path: Path):
        """
        兼容 Windows 中文路径的图片读取方式。

        不直接使用 cv2.imread(str(path))，因为 OpenCV 在 Windows 下
        读取包含中文的路径时可能返回 None。
        """
        try:
            file_bytes = np.fromfile(str(image_path), dtype=np.uint8)
        except Exception as e:
            raise ValueError(f"无法读取图片文件字节: {image_path}，原因: {e}")

        if file_bytes.size == 0:
            raise ValueError(f"图片文件为空: {image_path}")

        image = cv2.imdecode(file_bytes, cv2.IMREAD_GRAYSCALE)

        if image is None:
            raise ValueError(f"OpenCV 解码失败: {image_path}")

        return image

    def _read_image_size(self, image_path: Path):
        """
        使用 PIL 读取图片尺寸，同时做基础完整性检查。
        """
        try:
            with Image.open(image_path) as img:
                img.verify()

            with Image.open(image_path) as img:
                img.load()
                width, height = img.size

            return width, height

        except UnidentifiedImageError as e:
            raise ValueError(f"PIL 无法识别图片格式: {image_path}，原因: {e}")
        except OSError as e:
            raise ValueError(f"PIL 无法读取图片: {image_path}，原因: {e}")

    def _calc_blur_score(self, image_path: Path):
        """
        使用拉普拉斯方差估计图片清晰度。
        分数越低，说明图片越可能模糊。
        """
        image = self._read_image_gray(image_path)
        score = cv2.Laplacian(image, cv2.CV_64F).var()
        return float(score)

    def _scan_one_dir(
        self,
        title: str,
        image_path: Path,
        min_images: int,
        blur_threshold: float,
    ):
        result = {
            "title": title,
            "path": str(image_path),
            "total_images": 0,
            "readable_images": 0,
            "main_resolution": "无",
            "avg_blur_score": 0.0,
            "resolution_counter": Counter(),
            "unreadable_images": [],
            "blur_images": [],
            "warnings": [],
        }

        if not image_path.exists():
            result["warnings"].append(f"{title}目录不存在，跳过检查。")
            return result

        if not image_path.is_dir():
            result["warnings"].append(f"{title}路径不是文件夹，跳过检查。")
            return result

        images = self._collect_images(image_path)
        result["total_images"] = len(images)

        if len(images) == 0:
            result["warnings"].append(f"{title}目录中没有找到图片。")
            return result

        blur_score_sum = 0.0
        readable_count = 0

        for img_path in images:
            try:
                width, height = self._read_image_size(img_path)
                result["resolution_counter"][f"{width}x{height}"] += 1

                blur_score = self._calc_blur_score(img_path)
                blur_score_sum += blur_score
                readable_count += 1

                if blur_score < blur_threshold:
                    result["blur_images"].append((img_path.name, blur_score))

            except Exception as e:
                result["unreadable_images"].append(f"{img_path.name}: {e}")

        result["readable_images"] = readable_count

        if readable_count > 0:
            result["avg_blur_score"] = blur_score_sum / readable_count
        else:
            result["avg_blur_score"] = 0.0

        if len(images) < min_images:
            result["warnings"].append(
                f"{title}图片数量过少：当前 {len(images)} 张，建议不少于 {min_images} 张。"
            )

        if len(result["resolution_counter"]) > 1:
            result["warnings"].append(
                f"{title}图片分辨率不一致，可能影响后续流程稳定性。"
            )

        if len(result["unreadable_images"]) > 0:
            result["warnings"].append(
                f"{title}存在损坏或不可读取图片，共 {len(result['unreadable_images'])} 张。"
            )

        if len(result["blur_images"]) > 0:
            result["warnings"].append(
                f"{title}检测到可能模糊的图片，共 {len(result['blur_images'])} 张。"
            )

        if result["resolution_counter"]:
            result["main_resolution"] = result["resolution_counter"].most_common(1)[0][0]

        return result

    def _append_report_block(self, summary_lines, report):
        summary_lines.append(f"--- {report['title']} ---")
        summary_lines.append(f"目录: {report['path']}")
        summary_lines.append(f"图片总数: {report['total_images']}")
        summary_lines.append(f"可读取图片数: {report.get('readable_images', 0)}")
        summary_lines.append(f"主分辨率: {report['main_resolution']}")

        if report.get("readable_images", 0) > 0:
            summary_lines.append(f"平均清晰度分数: {report['avg_blur_score']:.4f}")
        else:
            summary_lines.append("平均清晰度分数: 未计算，原因是没有可读取图片")

        summary_lines.append("")

        summary_lines.append("分辨率统计：")
        if report["resolution_counter"]:
            for resolution, count in report["resolution_counter"].items():
                summary_lines.append(f"  - {resolution}: {count} 张")
        else:
            summary_lines.append("  - 无")

        summary_lines.append("")
        summary_lines.append("警告信息：")
        if report["warnings"]:
            for warning in report["warnings"]:
                summary_lines.append(f"  - {warning}")
        else:
            summary_lines.append("  - 无")

        summary_lines.append("")
        summary_lines.append("损坏或不可读取图片：")
        if report["unreadable_images"]:
            for item in report["unreadable_images"]:
                summary_lines.append(f"  - {item}")
        else:
            summary_lines.append("  - 无")

        summary_lines.append("")
        summary_lines.append("可能模糊的图片：")
        if report["blur_images"]:
            for name, score in report["blur_images"]:
                summary_lines.append(f"  - {name}: {score:.2f}")
        else:
            summary_lines.append("  - 无")

        summary_lines.append("")
        summary_lines.append("")

    def run(self):
        scene_name = self.preflight_cfg["scene_name"]
        raw_image_path = self._resolve_user_path(self.preflight_cfg["raw_image_path"])
        processed_image_path = self._resolve_user_path(
            self.preflight_cfg["processed_image_path"]
        )

        min_images = int(self.preflight_cfg.get("min_images", 10))
        blur_threshold = float(self.preflight_cfg.get("blur_threshold", 100.0))
        fail_on_unreadable = bool(self.preflight_cfg.get("fail_on_unreadable", True))

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "preflight.log"
        report_file = log_dir / "preflight_report.txt"
        logger = setup_logger(str(log_file))

        logger.info("开始执行数据预检查")
        logger.info("场景名称: %s", scene_name)
        logger.info("原始图片目录: %s", raw_image_path)
        logger.info("训练图片目录: %s", processed_image_path)
        logger.info("最少图片数要求: %s", min_images)
        logger.info("模糊检测阈值: %s", blur_threshold)
        logger.info("发现坏图是否终止: %s", fail_on_unreadable)

        raw_report = self._scan_one_dir(
            "原始数据",
            raw_image_path,
            min_images,
            blur_threshold,
        )

        processed_report = self._scan_one_dir(
            "训练数据",
            processed_image_path,
            min_images,
            blur_threshold,
        )

        reports = [raw_report, processed_report]

        summary_lines = []
        summary_lines.append("========== 数据预检查报告 ==========")
        summary_lines.append(f"场景名称: {scene_name}")
        summary_lines.append(f"模糊检测阈值: {blur_threshold}")
        summary_lines.append("")

        for report in reports:
            self._append_report_block(summary_lines, report)

        report_text = "\n".join(summary_lines)

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_text)

        print(report_text)
        logger.info(report_text)
        logger.info("数据预检查完成，报告已保存到: %s", report_file)

        total_bad = sum(len(report["unreadable_images"]) for report in reports)

        if fail_on_unreadable and total_bad > 0:
            raise RuntimeError(
                f"预检查发现 {total_bad} 张损坏或不可读取图片，请先清理后再继续。"
            )

        print(f"\n数据预检查完成，报告已保存到: {report_file}")

        return {
            "scene_name": scene_name,
            "raw_report": raw_report,
            "processed_report": processed_report,
            "report_file": str(report_file),
        }


if __name__ == "__main__":
    service = PreflightService()
    service.run()