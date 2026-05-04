from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Sequence


class ImmediateStopRequested(RuntimeError):
    """当前任务被用户请求立即停止。"""


class ProcessRegistry:
    """记录任务正在运行的外部子进程，用于立即停止。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: Dict[str, List[subprocess.Popen[Any]]] = {}
        self._force_stop_task_ids: set[str] = set()

    def register(self, task_id: Optional[str], process: subprocess.Popen[Any]) -> None:
        if not task_id:
            return
        with self._lock:
            self._processes.setdefault(task_id, []).append(process)

    def unregister(self, task_id: Optional[str], process: subprocess.Popen[Any]) -> None:
        if not task_id:
            return
        with self._lock:
            processes = self._processes.get(task_id)
            if not processes:
                return
            self._processes[task_id] = [item for item in processes if item is not process]
            if not self._processes[task_id]:
                self._processes.pop(task_id, None)

    def request_force_stop(self, task_id: str) -> int:
        """标记立即停止并终止当前任务的全部活跃子进程。返回尝试终止的进程数。"""
        with self._lock:
            self._force_stop_task_ids.add(task_id)
            processes = list(self._processes.get(task_id, []))

        terminated = 0
        for process in processes:
            if process.poll() is not None:
                continue
            terminated += 1
            terminate_process_tree(process)
        return terminated

    def is_force_stop_requested(self, task_id: Optional[str]) -> bool:
        if not task_id:
            return False
        with self._lock:
            return task_id in self._force_stop_task_ids

    def clear_force_stop(self, task_id: str) -> None:
        with self._lock:
            self._force_stop_task_ids.discard(task_id)

    def clear_task(self, task_id: str) -> None:
        with self._lock:
            self._processes.pop(task_id, None)
            self._force_stop_task_ids.discard(task_id)


process_registry = ProcessRegistry()


def build_popen_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """让子进程拥有独立进程组，便于立即停止时终止进程树。"""
    result = dict(kwargs)
    if os.name == "nt":
        result["creationflags"] = result.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        result.setdefault("start_new_session", True)
    return result


def popen_registered(
    task_id: Optional[str],
    cmd: Sequence[str],
    **kwargs: Any,
) -> subprocess.Popen[Any]:
    process = subprocess.Popen(cmd, **build_popen_kwargs(kwargs))
    process_registry.register(task_id, process)
    return process


def terminate_process_tree(process: subprocess.Popen[Any], timeout: float = 3.0) -> None:
    """跨平台尽量终止子进程及其进程组。"""
    if process.poll() is not None:
        return

    try:
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except Exception:
                process.terminate()
    except Exception:
        try:
            process.kill()
        except Exception:
            return

    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.1)

    if process.poll() is None:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


def raise_if_force_stopped(task_id: Optional[str]) -> None:
    if process_registry.is_force_stop_requested(task_id):
        raise ImmediateStopRequested("已收到立即停止请求，当前子进程已被终止")
