from pathlib import Path
import subprocess
import shutil

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger
from engine.core.process_utils import popen_registered, process_registry, raise_if_force_stopped


class VideoService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        video_config_path="configs/video.yaml",
        task_id: str | None = None,
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

    def run(self):
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

        output_pattern = output_images / "image%06d.png"

        cmd = [
            ffmpeg_executable,
            "-i", str(video_path),
            "-vf", f"fps={target_fps}",
            "-q:v", "2",
            str(output_pattern)
        ]

        logger.info("开始视频抽帧")
        logger.info("场景名称: %s", scene_name)
        logger.info("输入视频: %s", video_path)
        logger.info("输出目录: %s", output_images)
        logger.info("目标帧率: %s", target_fps)
        logger.info("执行命令: %s", " ".join(cmd))

        print("开始视频抽帧")
        print("输入视频:", video_path)
        print("输出目录:", output_images)
        print("目标帧率:", target_fps)

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

        try:
            for line in process.stdout:
                line = line.rstrip()
                print(line)
                logger.info(line)

            process.wait()
        finally:
            process_registry.unregister(self.task_id, process)

        raise_if_force_stopped(self.task_id)

        if process.returncode != 0:
            logger.error("视频抽帧失败，返回码: %s", process.returncode)
            raise RuntimeError(f"视频抽帧失败，返回码: {process.returncode}")

        logger.info("视频抽帧完成")
        print("视频抽帧完成")