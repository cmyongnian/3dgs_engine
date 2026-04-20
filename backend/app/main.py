from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="3DGS 平台后端",
        version="1.0.0",
        description="面向三维重建平台的任务调度与日志服务",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict:
        return {"message": "3DGS 平台后端已启动"}

    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
