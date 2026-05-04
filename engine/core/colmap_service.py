from pathlib import Path
import subprocess

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.logger import setup_logger
from engine.core.process_utils import popen_registered, process_registry, raise_if_force_stopped


class ColmapService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        colmap_config_path="configs/colmap.yaml",
        task_id: str | None = None,
    ):
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

        colmap_config_path = Path(colmap_config_path)
        if not colmap_config_path.is_absolute():
            colmap_config_path = self.pm.project_root / colmap_config_path

        self.colmap_cfg = load_yaml(str(colmap_config_path))["colmap"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _resolve_executable(self, exe: str) -> str:
        exe_path = Path(exe)
        if exe_path.is_absolute():
            return str(exe_path)

        # 如果写的是相对路径，例如 third_party/colmap/COLMAP.bat
        if any(sep in exe for sep in ["/", "\\"]):
            return str((self.pm.project_root / exe_path).resolve())

        # 如果只是 "colmap"，就交给系统 PATH 查找
        return exe

    def _check_image_folder(self, image_path: Path):
        if not image_path.exists():
            raise FileNotFoundError(f"原始图像目录不存在: {image_path}")

        if not image_path.is_dir():
            raise NotADirectoryError(f"image_path 不是文件夹: {image_path}")

        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        images = [p for p in image_path.iterdir() if p.suffix.lower() in image_exts]

        if len(images) == 0:
            raise RuntimeError(f"原始图像目录中没有找到图片: {image_path}")

    def run(self):
        scene_name = self.colmap_cfg["scene_name"]
        image_path = self._resolve_user_path(self.colmap_cfg["image_path"])
        workspace_path = self._resolve_user_path(self.colmap_cfg["workspace_path"])
        colmap_executable = self._resolve_executable(
            self.colmap_cfg.get("colmap_executable", "colmap")
        )
        use_gpu = self.colmap_cfg.get("use_gpu", True)

        self._check_image_folder(image_path)

        workspace_path.mkdir(parents=True, exist_ok=True)

        log_dir = self.pm.scene_log(scene_name)
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "colmap.log"
        logger = setup_logger(str(log_file))

        cmd = [
            str(colmap_executable),
            "automatic_reconstructor",
            "--workspace_path", str(workspace_path),
            "--image_path", str(image_path),
            "--use_gpu", "1" if use_gpu else "0",
        ]

        logger.info("开始 COLMAP 重建")
        logger.info("项目根目录: %s", self.pm.project_root)
        logger.info("场景名称: %s", scene_name)
        logger.info("原始图像目录: %s", image_path)
        logger.info("工作目录: %s", workspace_path)
        logger.info("COLMAP 可执行程序: %s", colmap_executable)
        logger.info("执行命令: %s", " ".join(cmd))

        print("开始 COLMAP 重建")
        print("项目根目录:", self.pm.project_root)
        print("原始图像目录:", image_path)
        print("工作目录:", workspace_path)
        print("COLMAP 可执行程序:", colmap_executable)
        print("执行命令:", " ".join(cmd))

        try:
            process = popen_registered(
                self.task_id,
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"找不到 COLMAP 可执行程序: {colmap_executable}\n"
                f"请检查 configs/colmap.yaml 里的 colmap_executable 配置。"
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

        if process.returncode == 0:
            logger.info("COLMAP 重建完成")
            print("COLMAP 重建完成")
        else:
            logger.error("COLMAP 重建失败，返回码: %s", process.returncode)
            raise RuntimeError(f"COLMAP 重建失败，返回码: {process.returncode}")