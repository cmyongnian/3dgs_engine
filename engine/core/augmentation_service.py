from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, List, Optional

import cv2
import numpy as np

from engine.core.config import load_yaml
from engine.core.logger import setup_logger
from engine.core.paths import PathManager
from engine.core.process_utils import raise_if_force_stopped

try:
    import albumentations as A
except Exception:
    A = None  # type: ignore


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass
class AugmentationItem:
    filename: str
    status: str
    message: str = ""


class AugmentationService:
    """
    3DGS 安全型数据增强服务。

    只做 pixel-level / image-only 增强：
    - 白平衡
    - CLAHE 局部对比度增强
    - Gamma 校正
    - 轻度去噪
    - 轻度锐化

    不做裁剪、旋转、翻转、仿射等几何增强，避免破坏 COLMAP 相机位姿。
    """

    def __init__(
        self,
        system_config_path: str = "configs/system.yaml",
        augmentation_config_path: str = "configs/augmentation.yaml",
        task_id: Optional[str] = None,
    ) -> None:
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

        config_path = Path(augmentation_config_path)
        if not config_path.is_absolute():
            config_path = self.pm.project_root / config_path

        self.augmentation_cfg = load_yaml(str(config_path))["augmentation"]

    def _resolve_user_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path.resolve()
        return (self.pm.project_root / path).resolve()

    def _read_image(self, path: Path) -> np.ndarray:
        data = np.fromfile(str(path), dtype=np.uint8)
        image_bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise RuntimeError(f"无法读取图片: {path}")
        return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    def _write_image(self, path: Path, image_rgb: np.ndarray, jpeg_quality: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)

        suffix = path.suffix.lower()
        params: List[int] = []

        if suffix in {".jpg", ".jpeg"}:
            params = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]
        elif suffix == ".png":
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]

        ok, encoded = cv2.imencode(suffix if suffix else ".jpg", image_bgr, params)
        if not ok:
            raise RuntimeError(f"无法编码图片: {path}")

        encoded.tofile(str(path))

    def _iter_images(self, input_dir: Path) -> Iterable[Path]:
        for item in sorted(input_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in IMAGE_EXTS:
                yield item

    def _gray_world_white_balance(self, image: np.ndarray) -> np.ndarray:
        image_f = image.astype(np.float32)
        channel_means = image_f.reshape(-1, 3).mean(axis=0)
        gray_mean = float(channel_means.mean())
        scale = gray_mean / np.maximum(channel_means, 1e-6)
        balanced = image_f * scale.reshape(1, 1, 3)
        return np.clip(balanced, 0, 255).astype(np.uint8)

    def _auto_gamma(self, image: np.ndarray, target_mean: float = 0.48) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
        mean = float(np.clip(gray.mean(), 1e-4, 0.9999))
        gamma = np.log(target_mean) / np.log(mean)
        gamma = float(np.clip(gamma, 0.65, 1.60))

        table = np.array(
            [((i / 255.0) ** gamma) * 255.0 for i in range(256)],
            dtype=np.uint8,
        )
        return cv2.LUT(image, table)

    def _denoise(self, image: np.ndarray, h: float) -> np.ndarray:
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        denoised = cv2.fastNlMeansDenoisingColored(
            bgr,
            None,
            h=float(h),
            hColor=float(h),
            templateWindowSize=7,
            searchWindowSize=21,
        )
        return cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB)

    def _sharpen(self, image: np.ndarray, amount: float) -> np.ndarray:
        amount = float(np.clip(amount, 0.0, 1.0))
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=1.1)
        sharpened = cv2.addWeighted(image, 1.0 + amount, blurred, -amount, 0)
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    def _resize_long_edge(self, image: np.ndarray, max_long_edge: int) -> np.ndarray:
        if max_long_edge <= 0:
            return image

        height, width = image.shape[:2]
        long_edge = max(height, width)

        if long_edge <= max_long_edge:
            return image

        scale = max_long_edge / float(long_edge)
        new_size = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)

    def _opencv_clahe(self, image: np.ndarray) -> np.ndarray:
        tile_grid_size = self.augmentation_cfg.get("clahe_tile_grid_size", [8, 8])
        if not isinstance(tile_grid_size, (list, tuple)) or len(tile_grid_size) != 2:
            tile_grid_size = [8, 8]

        lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(
            clipLimit=float(self.augmentation_cfg.get("clahe_clip_limit", 2.0)),
            tileGridSize=(int(tile_grid_size[0]), int(tile_grid_size[1])),
        )
        l_channel = clahe.apply(l_channel)
        merged = cv2.merge((l_channel, a_channel, b_channel))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)

    def _build_albumentations_pipeline(self) -> Optional[Any]:
        if A is None:
            return None

        transforms = []

        if self.augmentation_cfg.get("clahe", True):
            tile_grid_size = self.augmentation_cfg.get("clahe_tile_grid_size", [8, 8])
            if not isinstance(tile_grid_size, (list, tuple)) or len(tile_grid_size) != 2:
                tile_grid_size = [8, 8]

            transforms.append(
                A.CLAHE(
                    clip_limit=float(self.augmentation_cfg.get("clahe_clip_limit", 2.0)),
                    tile_grid_size=(int(tile_grid_size[0]), int(tile_grid_size[1])),
                    p=1.0,
                )
            )

        if not transforms:
            return None

        return A.Compose(transforms)

    def _augment_one(self, image: np.ndarray, pipeline: Optional[Any]) -> np.ndarray:
        if self.augmentation_cfg.get("gray_world", True):
            image = self._gray_world_white_balance(image)

        if self.augmentation_cfg.get("auto_gamma", False):
            image = self._auto_gamma(
                image,
                target_mean=float(self.augmentation_cfg.get("gamma_target_mean", 0.48)),
            )

        if pipeline is not None:
            image = pipeline(image=image)["image"]
        elif self.augmentation_cfg.get("clahe", True):
            image = self._opencv_clahe(image)

        if self.augmentation_cfg.get("denoise", False):
            image = self._denoise(
                image,
                h=float(self.augmentation_cfg.get("denoise_h", 3.0)),
            )

        if self.augmentation_cfg.get("sharpen", False):
            image = self._sharpen(
                image,
                amount=float(self.augmentation_cfg.get("sharpen_amount", 0.25)),
            )

        max_long_edge = int(self.augmentation_cfg.get("max_long_edge", 0) or 0)
        image = self._resize_long_edge(image, max_long_edge=max_long_edge)

        return image

    def _write_reports(
        self,
        log_dir: Path,
        scene_name: str,
        input_dir: Path,
        output_dir: Path,
        items: List[AugmentationItem],
    ) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)

        ok_count = sum(1 for item in items if item.status == "success")
        failed_count = sum(1 for item in items if item.status == "failed")
        skipped_count = sum(1 for item in items if item.status == "skipped")

        report = {
            "scene_name": scene_name,
            "input_images": str(input_dir),
            "output_images": str(output_dir),
            "total": len(items),
            "success": ok_count,
            "failed": failed_count,
            "skipped": skipped_count,
            "method": {
                "library": "Albumentations",
                "type": "pixel-level/image-only safe augmentation for 3DGS",
                "geometric_transforms": False,
                "operations": {
                    "gray_world": bool(self.augmentation_cfg.get("gray_world", True)),
                    "clahe": bool(self.augmentation_cfg.get("clahe", True)),
                    "auto_gamma": bool(self.augmentation_cfg.get("auto_gamma", False)),
                    "denoise": bool(self.augmentation_cfg.get("denoise", False)),
                    "sharpen": bool(self.augmentation_cfg.get("sharpen", False)),
                    "max_long_edge": int(self.augmentation_cfg.get("max_long_edge", 0) or 0),
                },
            },
            "items": [asdict(item) for item in items],
        }

        json_path = log_dir / "augmentation_report.json"
        txt_path = log_dir / "augmentation_report.txt"

        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        txt_lines = [
            "3DGS 数据增强报告",
            f"场景名称: {scene_name}",
            f"输入目录: {input_dir}",
            f"输出目录: {output_dir}",
            f"总图片数: {len(items)}",
            f"成功: {ok_count}",
            f"失败: {failed_count}",
            f"跳过: {skipped_count}",
            "增强类型: pixel-level/image-only，不使用裁剪、旋转、翻转、仿射等几何增强。",
        ]
        txt_path.write_text("\n".join(txt_lines), encoding="utf-8")

    def run(self) -> None:
        raise_if_force_stopped(self.task_id)

        enabled = bool(self.augmentation_cfg.get("enabled", True))
        scene_name = self.augmentation_cfg["scene_name"]
        input_dir = self._resolve_user_path(self.augmentation_cfg["input_images"])
        output_dir = self._resolve_user_path(self.augmentation_cfg["output_images"])
        overwrite = bool(self.augmentation_cfg.get("overwrite", True))
        keep_original_if_failed = bool(self.augmentation_cfg.get("keep_original_if_failed", True))
        jpeg_quality = int(self.augmentation_cfg.get("jpeg_quality", 95))

        log_dir_cfg = self.augmentation_cfg.get("log_dir", "")
        log_dir = self._resolve_user_path(log_dir_cfg) if log_dir_cfg else self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger = setup_logger(str(log_dir / "augmentation.log"))

        print("开始数据增强")
        print("场景名称:", scene_name)
        print("输入图片目录:", input_dir)
        print("输出图片目录:", output_dir)

        logger.info("开始数据增强")
        logger.info("场景名称: %s", scene_name)
        logger.info("输入图片目录: %s", input_dir)
        logger.info("输出图片目录: %s", output_dir)

        if not enabled:
            print("数据增强已关闭，跳过。")
            logger.info("数据增强已关闭，跳过。")
            return

        if A is None and bool(self.augmentation_cfg.get("clahe", True)):
            print("未检测到 Albumentations，自动使用 OpenCV CLAHE 兜底实现。")
            logger.warning("未检测到 Albumentations，自动使用 OpenCV CLAHE 兜底实现。")

        if not input_dir.exists() or not input_dir.is_dir():
            raise FileNotFoundError(f"数据增强输入目录不存在: {input_dir}")

        images = list(self._iter_images(input_dir))
        if not images:
            raise RuntimeError(f"数据增强输入目录中没有找到图片: {input_dir}")

        if overwrite and output_dir.exists():
            shutil.rmtree(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        pipeline = self._build_albumentations_pipeline()
        items: List[AugmentationItem] = []

        for index, image_path in enumerate(images, start=1):
            raise_if_force_stopped(self.task_id)

            output_path = output_dir / image_path.name

            try:
                image = self._read_image(image_path)
                augmented = self._augment_one(image, pipeline)
                self._write_image(output_path, augmented, jpeg_quality=jpeg_quality)

                items.append(AugmentationItem(filename=image_path.name, status="success"))

                line = f"[{index}/{len(images)}] 已增强: {image_path.name}"
                print(line)
                logger.info(line)

            except Exception as exc:
                message = str(exc)
                logger.exception("增强失败: %s", image_path)

                if keep_original_if_failed:
                    shutil.copy2(image_path, output_path)
                    items.append(
                        AugmentationItem(
                            filename=image_path.name,
                            status="skipped",
                            message=f"增强失败，已复制原图: {message}",
                        )
                    )
                    print(f"[{index}/{len(images)}] 增强失败，已复制原图: {image_path.name}")
                else:
                    items.append(
                        AugmentationItem(
                            filename=image_path.name,
                            status="failed",
                            message=message,
                        )
                    )
                    raise

        self._write_reports(log_dir, scene_name, input_dir, output_dir, items)

        success_count = sum(1 for item in items if item.status == "success")
        print(f"数据增强完成：成功 {success_count}/{len(items)}，输出目录：{output_dir}")
        logger.info(
            "数据增强完成：成功 %s/%s，输出目录：%s",
            success_count,
            len(items),
            output_dir,
        )