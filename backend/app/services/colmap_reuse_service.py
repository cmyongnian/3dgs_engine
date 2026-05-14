from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from backend.app.schemas.task import ColmapReuseOption
from backend.app.state.task_store import task_store


class ColmapReuseService:
    """扫描同名场景下可复用的 COLMAP 结果。

    目录约定：
    engine/datasets/processed/<scene_name>/<task_id>/database.db
    engine/datasets/processed/<scene_name>/<task_id>/sparse/0/{cameras,images,points3D}.bin

    为了兼容手动整理过的目录，也支持 sparse 目录中直接放 cameras/images/points3D。
    返回给前端的 workspace_path 尽量使用相对于 engine 的路径，例如：
    datasets/processed/liren/2b8a7d427d63
    这样 engine/core/colmap_service.py 可以按 engine 根目录直接解析。
    """

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.engine_root = self.project_root / "engine"

    @staticmethod
    def _safe_scene_name(scene_name: str) -> str:
        return str(scene_name or "").strip().replace("\\", "").replace("/", "")

    @staticmethod
    def _has_sparse_model_files(sparse_dir: Path) -> bool:
        if not sparse_dir.exists() or not sparse_dir.is_dir():
            return False

        bin_ok = all(
            (sparse_dir / name).exists()
            for name in ["cameras.bin", "images.bin", "points3D.bin"]
        )
        txt_ok = all(
            (sparse_dir / name).exists()
            for name in ["cameras.txt", "images.txt", "points3D.txt"]
        )
        return bin_ok or txt_ok

    def _locate_colmap_result(self, workspace: Path) -> Optional[Tuple[Path, Path]]:
        """返回 database.db 与 sparse 模型目录。"""
        candidates = [
            (workspace / "database.db", workspace / "sparse" / "0"),
            (workspace / "database.db", workspace / "sparse"),
            (workspace / "distorted" / "database.db", workspace / "distorted" / "sparse" / "0"),
            (workspace / "distorted" / "database.db", workspace / "distorted" / "sparse"),
        ]

        for database_path, sparse_path in candidates:
            if database_path.exists() and self._has_sparse_model_files(sparse_path):
                return database_path, sparse_path

        return None

    def _to_engine_relative(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.engine_root.resolve())).replace("\\", "/")
        except Exception:
            return str(path.resolve())

    @staticmethod
    def _time_text(path: Path) -> str:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            return ""

    def _task_metadata(self) -> Dict[str, Dict[str, Optional[str]]]:
        meta: Dict[str, Dict[str, Optional[str]]] = {}
        try:
            records = task_store.list()
        except Exception:
            return meta

        for task in records:
            meta[task.task_id] = {
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "status": task.status,
            }
        return meta

    def _candidate_roots(self, scene_name: str) -> Iterable[Path]:
        # 项目正常运行时使用 engine/datasets/processed。
        yield self.engine_root / "datasets" / "processed" / scene_name

        # 兼容有人手动把数据放在仓库根目录 datasets/processed 的情况。
        yield self.project_root / "datasets" / "processed" / scene_name

    def list_options(self, scene_name: str) -> List[ColmapReuseOption]:
        scene_name = self._safe_scene_name(scene_name)
        if not scene_name:
            return []

        metadata = self._task_metadata()
        items: List[ColmapReuseOption] = []
        seen: set[str] = set()

        for root in self._candidate_roots(scene_name):
            if not root.exists() or not root.is_dir():
                continue

            for workspace in root.iterdir():
                if not workspace.is_dir():
                    continue

                resolved_key = str(workspace.resolve()).lower()
                if resolved_key in seen:
                    continue
                seen.add(resolved_key)

                located = self._locate_colmap_result(workspace)
                if located is None:
                    continue

                database_path, sparse_path = located
                task_id = workspace.name
                meta = metadata.get(task_id, {})

                note_parts = []
                if meta.get("status"):
                    note_parts.append(f"任务状态：{meta['status']}")
                note_parts.append(f"修改时间：{self._time_text(workspace)}")

                items.append(
                    ColmapReuseOption(
                        scene_name=scene_name,
                        task_id=task_id,
                        workspace_path=self._to_engine_relative(workspace),
                        sparse_path=self._to_engine_relative(sparse_path),
                        database_path=self._to_engine_relative(database_path),
                        created_at=meta.get("created_at"),
                        updated_at=meta.get("updated_at") or self._time_text(workspace),
                        status=meta.get("status"),
                        source="task_store+filesystem" if meta else "filesystem",
                        note="；".join(note_parts),
                    )
                )

        items.sort(key=lambda item: item.updated_at or item.created_at or "", reverse=True)
        return items


colmap_reuse_service = ColmapReuseService()
