"""监控页能选的任务。开始时只跑选中的一个。"""

from app.tasks.baotu import run as run_baotu
from app.tasks.mijing import run as run_mijing
from app.tasks.shimen import run as run_shimen

TASKS = (
    {"id": "shimen", "name": "师门任务"},
    {"id": "baotu", "name": "宝图任务"},
    {"id": "mijing", "name": "秘境降妖"},
)


def list_tasks() -> list[dict[str, str]]:
    return [dict(item) for item in TASKS]


def task_name(task_id: str) -> str:
    for item in TASKS:
        if item["id"] == task_id:
            return item["name"]
    return ""


def run_task(slot, hwnd: int, task_id: str) -> None:
    if task_id == "shimen":
        run_shimen(slot, hwnd)
        return
    if task_id == "baotu":
        run_baotu(slot, hwnd)
        return
    if task_id == "mijing":
        run_mijing(slot, hwnd)
        return
    slot._set("已停止", "没有这个任务")
