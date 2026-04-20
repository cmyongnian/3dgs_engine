from pathlib import Path

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/layout")
def layout() -> dict:
    root = Path(__file__).resolve().parents[4]
    engine_root = root / "engine"
    return {
        "project_root": str(root),
        "engine_exists": engine_root.exists(),
        "backend_exists": (root / "backend").exists(),
        "frontend_exists": (root / "frontend").exists(),
        "engine_dirs": {
            "app": (engine_root / "app").exists(),
            "core": (engine_root / "core").exists(),
            "configs": (engine_root / "configs").exists(),
            "datasets": (engine_root / "datasets").exists(),
            "outputs": (engine_root / "outputs").exists(),
            "third_party": (engine_root / "third_party").exists(),
        },
    }
