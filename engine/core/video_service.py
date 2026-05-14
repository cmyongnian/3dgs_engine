from pathlib import Path
import subprocess
import shutil
from typing import Optional, List

from PIL import Image, UnidentifiedImageError

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger
from engine.core.process_utils import (
    popen_registered,
    process_registry,
    raise_if_force_stopped,
)


class VideoService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        video_config_path="configs/video.yaml",
        task_id: Optional[str] = None,
    ):
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

        video_config_path = Path(video_config_path)
        if not video_config_path.is_absolute():
            video_config_path = self.pm.project_root / video_config_path

        self.video_cfg = load_yaml(str(video_config_path))["video"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _resolve_executable(self, exe: str) -> str:
        if not exe:
            return ""

        exe_path = Path(exe)

        if exe_path.is_absolute():
            return str(exe_path)

        if any(sep in exe for sep in ["/", "\\"]):
            return str((self.pm.project_root / exe_path).resolve())

        return exe

    def _collect_images(self, image_dir: Path) -> List[Path]:
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        if not image_dir.exists():
            return []
        return sorted(
            [p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in image_exts],
            key=lambda x: x.name,
        )

    def _verify_image(self, image_path: Path) -> None:
        try:
            with Image.open(image_path) as img:
                img.verify()

            with Image.open(image_path) as img:
                img.load()
                if img.width <= 0 or img.height <= 0:
                    raise ValueError("图片宽高异常")
        except (UnidentifiedImageError, OSError, ValueError) as e:
            raise RuntimeError(f"图片校验失败: {image_path}，原因: {e}")

    def _normalize_to_jpeg(self, image_dir: Path, logger) -> int:
        """
        将 ffmpeg 抽出的帧统一整理成 COLMAP 更稳定支持的 RGB JPEG。

        之前使用 PNG 时，PIL/OpenCV 可以读取，但 COLMAP 在 Windows 下可能报：
        BITMAP_ERROR: Failed to read the image file format.
        因此这里统一输出 image000001.jpg 这类 JPEG 文件，并在写入后立即校验。
        """
        raise_if_force_stopped(self.task_id)

        images = self._collect_images(image_dir)
        if not images:
            raise RuntimeError(f"视频抽帧后未找到任何图片: {image_dir}")

        normalized_count = 0
        temp_dir = image_dir.parent / f"{image_dir.name}_normalized_tmp"

        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            for index, src in enumerate(images, start=1):
                raise_if_force_stopped(self.task_id)

                dst = temp_dir / f"image{index:06d}.jpg"

                try:
                    with Image.open(src) as img:
                        img.load()
                        rgb = img.convert("RGB")
                        rgb.save(
                            dst,
                            format="JPEG",
                            quality=95,
                            optimize=False,
                            progressive=False,
                        )

                    self._verify_image(dst)
                    normalized_count += 1

                except Exception as e:
                    raise RuntimeError(f"抽帧图片规范化失败: {src} -> {dst}，原因: {e}")

            # 只有全部成功后才替换原输出目录，避免半途失败留下混乱文件。
            for old in image_dir.iterdir():
                if old.is_file():
                    old.unlink()
                elif old.is_dir():
                    shutil.rmtree(old)

            for item in sorted(temp_dir.iterdir(), key=lambda x: x.name):
                shutil.move(str(item), str(image_dir / item.name))

        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

        logger.info("抽帧图片已统一转换为 RGB JPEG，共 %s 张", normalized_count)
        print(f"抽帧图片已统一转换为 RGB JPEG，共 {normalized_count} 张")

        return normalized_count

    def run(self):
        raise_if_force_stopped(self.task_id)

        scene_name = self.video_cfg["scene_name"]
        video_path = self._resolve_user_path(self.video_cfg["video_path"])
        output_images = self._resolve_user_path(self.video_cfg["output_images"])
        ffmpeg_executable = self._resolve_executable(
            self.video_cfg.get("ffmpeg_executable", "ffmpeg")
        )
        target_fps = self.video_cfg.get("target_fps", 2)

        if not video_path.exists():
            raise FileNotFoundError(f"视频不存在: {video_path}")

        if output_images.exists():
            shutil.rmtree(output_images)

        output_images.mkdir(parents=True, exist_ok=True)

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "video_extract.log"
        logger = setup_logger(str(log_file))

        # 直接输出 jpg，避免 COLMAP 对部分 PNG 帧报 BITMAP_ERROR。
        output_pattern = output_images / "image%06d.jpg"

        vf = f"fps={target_fps},scale=trunc(iw/2)*2:trunc(ih/2)*2"

        cmd = [
            ffmpeg_executable,
            "-y",
            "-i",
            str(video_path),
            "-vf",
            vf,
            "-q:v",
            "2",
            "-start_number",
            "1",
            str(output_pattern),
        ]

        logger.info("开始视频抽帧")
        logger.info("场景名称: %s", scene_name)
        logger.info("输入视频: %s", video_path)
        logger.info("输出目录: %s", output_images)
        logger.info("目标帧率: %s", target_fps)
        logger.info("输出格式: RGB JPEG")
        logger.info("执行命令: %s", " ".join(cmd))

        print("开始视频抽帧")
        print("输入视频:", video_path)
        print("输出目录:", output_images)
        print("目标帧率:", target_fps)
        print("输出格式: RGB JPEG")
        print("执行命令:", " ".join(cmd))

        process = None

        try:
            try:
                process = popen_registered(
                    self.task_id,
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"找不到 ffmpeg 可执行程序: {ffmpeg_executable}\n"
                    "请检查 video.yaml 中的 ffmpeg_executable 配置。"
                )

            if process.stdout:
                for line in process.stdout:
                    raise_if_force_stopped(self.task_id)

                    line = line.rstrip()
                    if line:
                        print(line)
                        logger.info(line)

            process.wait()

            raise_if_force_stopped(self.task_id)

            if process.returncode != 0:
                logger.error("视频抽帧失败，返回码: %s", process.returncode)
                raise RuntimeError(f"视频抽帧失败，返回码: {process.returncode}")

            frame_count = self._normalize_to_jpeg(output_images, logger)

            logger.info("视频抽帧完成，共生成 %s 张可用于 COLMAP 的 JPEG 图片", frame_count)
            print(f"视频抽帧完成，共生成 {frame_count} 张可用于 COLMAP 的 JPEG 图片")

            return {
                "scene_name": scene_name,
                "video_path": str(video_path),
                "output_images": str(output_images),
                "target_fps": target_fps,
                "frame_count": frame_count,
                "image_format": "jpg",
            }

        finally:
            if process is not None:
                process_registry.unregister(self.task_id, process)
