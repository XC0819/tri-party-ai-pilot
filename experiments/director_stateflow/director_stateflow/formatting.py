"""Both views are projections of one current state, not independent claims."""

from datetime import timedelta, timezone

from .model import instant
from .process import poll_fact

LABEL = {"assigned": "等待 Codex 接单", "developing": "Codex 开发和测试中",
         "awaiting_review": "等待总监审计", "reviewing": "总监正在实际审计",
         "changes_requested": "审计要求返工，等待 Codex 领取", "reworking": "Codex 正在返工",
         "awaiting_rereview": "等待总监复审", "awaiting_user_approval": "技术通过，等待用户最终批准",
         "blocked": "已阻塞", "timed_out": "检查超时", "closed": "已按用户批准结束"}
ROLE = {"Codex": "本地 Codex", "ChatGPT": "ChatGPT 项目总监", "user": "用户"}
POLL = {"not_started": "未启动", "running": "真实运行中", "stopped": "已停止",
        "timeout": "已超时停止", "error": "验证失败/异常"}


def one_line(text):
    return " ".join(str(text).splitlines())


def footer(event, record=None, now=None, synced=True):
    effective, detail = poll_fact(event, record, now)
    stamp = instant(event.updated_at).astimezone(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    completed = "；".join(one_line(x) for x in event.completed) or "尚无已完成事项记录"
    return (f"【协作状态｜{event.task_id}】\n"
            f"阶段：{LABEL[event.status]} `{event.status}`（里程碑 {event.milestones_done}/{event.milestones_total}；子任务：{one_line(event.subtask)}）\n"
            f"当前责任方：{ROLE[event.owner]}\n已完成：{completed}\n"
            f"下一步：{one_line(event.next_action)}\n触发条件：{one_line(event.trigger)}\n"
            f"定时检查：{POLL[effective]}（{detail}）\n"
            f"审计通知：{ {'not_sent': '待发送', 'sent': '已送达', 'failed': '发送失败'}[event.notification_status]}\n"
            f"PR / SHA：{event.pr_url} / {event.head_sha}；轮次：{event.round}\n"
            f"最后证据：{event.evidence_url}；seq={event.seq}；{'已同步 GitHub' if synced else '尚未同步 GitHub'}\n"
            f"更新时间：{stamp}")


def summary(event, view="codex", record=None, now=None, synced=True, sample=False):
    if view not in {"codex", "director"}:
        raise ValueError("view must be codex or director")
    prefix = "示例（虚构数据，不是实际日志）：\n\n" if sample else ""
    lead = "总监摘要：依据共享状态记录进行技术决策；网页端没有自动后台监视。" if view == "director" else "Codex 摘要：依据已完成里程碑和真实检查记录报告执行状态。"
    return prefix + lead + "\n\n" + footer(event, record, now, synced)
