from pathlib import Path
import subprocess
import os
from typing import Optional

from engine.core.config import load_yaml
from engine.core.paths import PathManager
from engine.core.process_utils import (
    popen_registered,
    process_registry,
    raise_if_force_stopped,
)


class ViewerService:
    def __init__(
        self,
        system_config_path="configs/system.yaml",
        viewer_config_path="configs/viewer.yaml",
        task_id: Optional[str] = None,
    ):
        self.pm = PathManager(system_config_path)
        self.task_id = task_id

        viewer_config_path = Path(viewer_config_path)
        if not viewer_config_path.is_absolute():
            viewer_config_path = self.pm.project_root / viewer_config_path

        self.viewer_cfg = load_yaml(str(viewer_config_path))["viewer"]

    def _resolve_user_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.pm.project_root / p).resolve()

    def _find_realtime_viewer_exe(self, viewer_root: Path) -> Path:
        candidates = [
            viewer_root / "bin" / "SIBR_gaussianViewer_app.exe",
            viewer_root / "bin" / "SIBR_gaussianViewer_app_config.exe",
            viewer_root / "SIBR_gaussianViewer_app.exe",
            viewer_root / "SIBR_gaussianViewer_app_config.exe",
        ]

        for exe in candidates:
            if exe.exists():
                return exe

        raise FileNotFoundError(
            f"未找到官方 Real-Time Viewer 可执行文件，请检查 viewer_root: {viewer_root}"
        )

    def run(self):
        raise_if_force_stopped(self.task_id)

        mode = self.viewer_cfg.get("mode", "realtime")

        if mode != "realtime":
            raise ValueError("当前只支持 realtime 模式")

        viewer_root = self._resolve_user_path(self.viewer_cfg["viewer_root"])
        model_path = self._resolve_user_path(self.viewer_cfg["model_path"])
        source_path = self._resolve_user_path(self.viewer_cfg["source_path"])

        rendering_width = self.viewer_cfg.get("rendering_width", 1200)
        rendering_height = self.viewer_cfg.get("rendering_height", 800)
        force_aspect_ratio = self.viewer_cfg.get("force_aspect_ratio", False)
        load_images = self.viewer_cfg.get("load_images", False)
        device = self.viewer_cfg.get("device", 0)

        wait_until_close = self.viewer_cfg.get("wait_until_close", False)
        detached = self.viewer_cfg.get("detached", True)

        if not viewer_root.exists():
            raise FileNotFoundError(f"viewer_root 不存在: {viewer_root}")

        if not model_path.exists():
            raise FileNotFoundError(f"模型目录不存在: {model_path}")

        if not source_path.exists():
            raise FileNotFoundError(f"训练输入目录不存在: {source_path}")

        viewer_exe = self._find_realtime_viewer_exe(viewer_root)

        cmd = [
            str(viewer_exe),
            "-m",
            str(model_path),
            "-s",
            str(source_path),
            "--rendering-size",
            str(rendering_width),
            str(rendering_height),
            "--device",
            str(device),
        ]

        if force_aspect_ratio:
            cmd.append("--force-aspect-ratio")

        if load_images:
            cmd.append("--load_images")

        print("即将启动官方 Real-Time Viewer")
        print("Viewer 根目录:", viewer_root)
        print("模型目录:", model_path)
        print("训练输入目录:", source_path)
        print("执行命令:", " ".join(cmd))

        popen_kwargs = {
            "cwd": str(viewer_exe.parent),
        }

        if detached and os.name == "nt":
            popen_kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            popen_kwargs["stdin"] = subprocess.DEVNULL
            popen_kwargs["stdout"] = subprocess.DEVNULL
            popen_kwargs["stderr"] = subprocess.DEVNULL

        process = None

        try:
            process = popen_registered(self.task_id, cmd, **popen_kwargs)

            if wait_until_close and not detached:
                process.wait()
                raise_if_force_stopped(self.task_id)
                print("Viewer 已关闭，程序结束")
            else:
                print("Viewer 已启动，任务流程继续。")

        finally:
            if process is not None:
                process_registry.unregister(self.task_id, process)