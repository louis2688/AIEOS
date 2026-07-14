from __future__ import annotations

from aeios.core.types import TaskStatus

# Allowed transitions for the Phase 1 task lifecycle.
ALLOWED: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.PLANNING, TaskStatus.FAILED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.FAILED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
}


class InvalidTransition(ValueError):
    pass


def can_transition(current: TaskStatus, nxt: TaskStatus) -> bool:
    if current == nxt:
        return True
    return nxt in ALLOWED.get(current, set())


def transition(current: TaskStatus, nxt: TaskStatus) -> TaskStatus:
    if not can_transition(current, nxt):
        raise InvalidTransition(f"Cannot transition {current.value} → {nxt.value}")
    return nxt
