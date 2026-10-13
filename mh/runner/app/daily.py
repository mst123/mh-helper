"""每个角色每天的日常完成记录。师门和其他每日一次的任务共用这一份。"""

import json
import threading
from datetime import date
from pathlib import Path

from app.config import ROOT

_PATH = Path(ROOT) / "data" / "daily.json"
_LOCK = threading.Lock()


def _load() -> dict:
    if not _PATH.exists():
        return {"characters": {}}
    try:
        raw = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"characters": {}}
    if not isinstance(raw, dict):
        return {"characters": {}}
    characters = raw.get("characters")
    if not isinstance(characters, dict):
        raw["characters"] = {}
    return raw


def _save(data: dict) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_profile(character_id: str, name: str, school: str) -> None:
    """记下角色 ID、名字和门派。ID 是唯一键。"""
    if not character_id:
        return
    with _LOCK:
        data = _load()
        row = data["characters"].setdefault(character_id, {})
        if name:
            row["name"] = name
        if school:
            row["school"] = school
        row.setdefault("tasks", {})
        _save(data)


def mark_done(character_id: str, task: str, day: str | None = None) -> None:
    """把某个日常记成当天已完成。同一天重复记也还是完成。"""
    if not character_id or not task:
        return
    day = day or date.today().isoformat()
    with _LOCK:
        data = _load()
        row = data["characters"].setdefault(character_id, {})
        tasks = row.setdefault("tasks", {})
        today = tasks.setdefault(day, {})
        if not isinstance(today, dict):
            today = {}
            tasks[day] = today
        today[task] = "完成"
        _save(data)


def clear_today(character_id: str, day: str | None = None) -> None:
    """清掉这个角色当天的完成标记。角色档案还在。"""
    if not character_id:
        return
    day = day or date.today().isoformat()
    with _LOCK:
        data = _load()
        row = data["characters"].get(character_id)
        if not isinstance(row, dict):
            return
        tasks = row.get("tasks")
        if isinstance(tasks, dict):
            tasks.pop(day, None)
        _save(data)


def is_done(character_id: str, task: str, day: str | None = None) -> bool:
    if not character_id or not task:
        return False
    day = day or date.today().isoformat()
    data = _load()
    row = data["characters"].get(character_id) or {}
    tasks = row.get("tasks") or {}
    today = tasks.get(day) or {}
    if not isinstance(today, dict):
        return False
    return today.get(task) == "完成"
