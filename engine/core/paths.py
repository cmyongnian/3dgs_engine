from pathlib import Path
from core.config import load_yaml


class PathManager:
    def __init__(self, system_config_path=None):
        self.project_root = Path(__file__).resolve().parent.parent

        if system_config_path is None:
            system_config_path = self.project_root / "configs" / "system.yaml"
        else:
            system_config_path = Path(system_config_path)
            if not system_config_path.is_absolute():
                system_config_path = self.project_root / system_config_path

        cfg = load_yaml(str(system_config_path))

        self.gs_repo = self._resolve_path(cfg["paths"]["gs_repo"])
        self.raw_data = self._resolve_path(cfg["paths"]["raw_data"])
        self.processed_data = self._resolve_path(cfg["paths"]["processed_data"])
        self.outputs = self._resolve_path(cfg["paths"]["outputs"])
        self.logs = self._resolve_path(cfg["paths"]["logs"])
        self.videos_data = self._resolve_path(cfg["paths"]["videos_data"])

    def _resolve_path(self, p: str) -> Path:
        p = Path(p)
        if p.is_absolute():
            return p
        return (self.project_root / p).resolve()

    def scene_raw(self, scene_name: str):
        return self.raw_data / scene_name

    def scene_processed(self, scene_name: str):
        return self.processed_data / scene_name

    def scene_output(self, scene_name: str):
        return self.outputs / scene_name

    def scene_log(self, scene_name: str):
        return self.logs / scene_name

    def scene_video(self, scene_name: str, suffix=".mp4"):
        return self.videos_data / f"{scene_name}{suffix}"