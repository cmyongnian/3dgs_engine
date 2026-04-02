from pathlib import Path
from collections import Counter
from PIL import Image, UnidentifiedImageError
import cv2

from core.config import load_yaml
from core.paths import PathManager
from core.logger import setup_logger


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
        images = [
            p for p in image_path.iterdir()
            if p.is_file() and p.suffix.lower() in image_exts
        ]
        return sorted(images)

    def _calc_blur_score(self, image_path: Path):
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"OpenCV 无法读取图片: {image_path}")
        return cv2.Laplacian(image, cv2.CV_64F).var()

    def run(self):
        scene_name = self.preflight_cfg["scene_name"]
        image_path = self._resolve_user_path(self.preflight_cfg["image_path"])
        min_images = int(self.preflight_cfg.get("min_images", 10))
        blur_threshold = float(self.preflight_cfg.get("blur_threshold", 100.0))

        if not image_path.exists():
            raise FileNotFoundError(f"图片目录不存在: {image_path}")

        if not image_path.is_dir():
            raise NotADirectoryError(f"image_path 不是文件夹: {image_path}")

        images = self._collect_images(image_path)
        if len(images) == 0:
            raise RuntimeError(f"图片目录中没有找到图片: {image_path}")

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "preflight.log"
        report_file = log_dir / "preflight_report.txt"
        logger = setup_logger(str(log_file))

        logger.info("开始执行数据预检查")
        logger.info("场景名称: %s", scene_name)
        logger.info("图片目录: %s", image_path)
        logger.info("最少图片数要求: %s", min_images)
        logger.info("模糊检测阈值: %s", blur_threshold)

        resolution_counter = Counter()
        unreadable_images = []
        blur_scores = []
        blur_images = []

        for img_path in images:
            try:
                with Image.open(img_path) as img:
                    width, height = img.size
                resolution_counter[f"{width}x{height}"] += 1

                blur_score = self._calc_blur_score(img_path)
                blur_scores.append((img_path.name, blur_score))

                if blur_score < blur_threshold:
                    blur_images.append((img_path.name, blur_score))

            except (UnidentifiedImageError, OSError, ValueError) as e:
                unreadable_images.append(f"{img_path.name}: {e}")

        warnings = []

        if len(images) < min_images:
            warnings.append(
                f"图片数量过少：当前 {len(images)} 张，建议不少于 {min_images} 张。"
            )

        if len(resolution_counter) > 1:
            warnings.append("图片分辨率不一致，可能影响后续 COLMAP 和训练稳定性。")

        if len(unreadable_images) > 0:
            warnings.append(f"存在无法读取的图片，共 {len(unreadable_images)} 张。")

        if len(blur_images) > 0:
            warnings.append(f"检测到可能模糊的图片，共 {len(blur_images)} 张。")

        if resolution_counter:
            main_resolution = resolution_counter.most_common(1)[0][0]
        else:
            main_resolution = "无"

        if blur_scores:
            avg_blur_score = sum(score for _, score in blur_scores) / len(blur_scores)
        else:
            avg_blur_score = 0.0

        summary_lines = [
            "========== 数据预检查报告 ==========",
            f"场景名称: {scene_name}",
            f"图片目录: {image_path}",
            f"图片总数: {len(images)}",
            f"主分辨率: {main_resolution}",
            f"模糊检测阈值: {blur_threshold}",
            f"平均清晰度分数: {avg_blur_score:.2f}",
            "",
            "分辨率统计：",
        ]

        for resolution, count in resolution_counter.items():
            summary_lines.append(f"  - {resolution}: {count} 张")

        summary_lines.append("")
        summary_lines.append("警告信息：")

        if warnings:
            for w in warnings:
                summary_lines.append(f"  - {w}")
        else:
            summary_lines.append("  - 无")

        summary_lines.append("")
        summary_lines.append("不可读取图片：")

        if unreadable_images:
            for item in unreadable_images:
                summary_lines.append(f"  - {item}")
        else:
            summary_lines.append("  - 无")

        summary_lines.append("")
        summary_lines.append("可能模糊的图片：")

        if blur_images:
            for name, score in blur_images:
                summary_lines.append(f"  - {name}: {score:.2f}")
        else:
            summary_lines.append("  - 无")

        report_text = "\n".join(summary_lines)

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_text)

        print(report_text)
        logger.info(report_text)
        logger.info("数据预检查完成，报告已保存到: %s", report_file)
        print(f"\n数据预检查完成，报告已保存到: {report_file}")