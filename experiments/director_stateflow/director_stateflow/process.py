"""Read-only OS identity checks; a JSON 'running' flag is not process evidence."""

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import os
from pathlib import Path

from .model import instant


def process_identity(pid):
    if type(pid) is not int or pid <= 0:
        return None
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        handle = kernel.OpenProcess(0x1000, False, pid)  # Query only; no termination permission.
        if not handle:
            return None
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return None
            return str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        # POSIX /proc start ticks distinguish a reused PID; no signal is sent.
        text = Path(f"/proc/{pid}/stat").read_text()
        return text[text.rfind(")") + 2:].split()[19]
    except (OSError, IndexError):
        return None


def poll_fact(event, record=None, now=None, inspect=process_identity):
    now = now or datetime.now(timezone.utc)
    if record is None:
        if event.poll_status in {"stopped", "timeout", "error"}:
            return event.poll_status, "最后事件记录已停止；没有宣称运行中"
        return "not_started", "拟运行/未验证启动" if event.poll_intent == "scheduled" else "未启动；无有效进程记录"
    if record.get("run_id") != event.poll_run_id or event.poll_run_id in {"none", "unknown"}:
        return "error", "检查运行标识不匹配"
    status = record.get("status")
    if status in {"stopped", "timeout", "error"}:
        return status, "实际进程结束记录优先于旧的运行声明"
    try:
        if status != "running":
            return "not_started", "仅已安排，尚未启动"
        deadline = instant(record["deadline"])
        if (record.get("task_id") != event.task_id or record.get("head_sha") != event.head_sha
                or record.get("round") != event.round or record.get("pr_number") != int(event.pr_url.rsplit("/", 1)[1])
                or record.get("interval_seconds") != event.poll_interval_seconds
                or instant(event.poll_deadline) != deadline):
            return "error", "运行记录与任务、PR、SHA、轮次或截止时间不一致"
        started = instant(record["started_at"])
        heartbeat = instant(record["heartbeat_at"])
        if deadline <= now:
            return "timeout", "实际记录已达到截止时间"
        if started > now or heartbeat > now or (now - heartbeat).total_seconds() > event.poll_interval_seconds + 30:
            return "error", "启动/心跳记录过期或来自未来"
        identity = inspect(record["pid"])
        if identity is None:
            return "stopped", "实际进程已结束或无法查询，不能报告运行中"
        if identity != record["process_identity"]:
            return "error", "PID 已复用或进程身份不符"
        return "running", f"已验证 PID {record['pid']}；只读检查每 {event.poll_interval_seconds} 秒；截止 {record['deadline']}"
    except (KeyError, TypeError, ValueError):
        return "error", "进程运行记录无效"
