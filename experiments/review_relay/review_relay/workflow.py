"""Decision contract from TASK-20261010-004."""


def decide_action(verdict: str, rework_count: int, max_reworks: int = 2) -> str:
    if verdict not in ("pending", "approve", "request_changes"):
        raise ValueError("unsupported verdict")
    if rework_count < 0 or max_reworks < 0:
        raise ValueError("rework counts must be nonnegative")
    if verdict == "pending":
        return "wait"
    if verdict == "approve":
        return "await_user_approval"
    if rework_count < max_reworks:
        return "rework"
    return "escalate"
