"""打开活动列表里的日常活动。师门、宝图和秘境共用这一段。"""

import time

from app.windows.capture import CaptureError
from app.windows.input import click_client_ratio, press_escape
from app.windows.ocr import read_texts_in
from app.toolkit.screen import compact, on_state_a

_ACTIVITY_CLICK = (0.3045, 0.1105)
_ACTIVITY_TITLE = (0.450, 0.166, 0.550, 0.228)
_DAILY_CLICK = (0.1355, 0.277)
SEARCH = (0.228, 0.240, 0.938, 0.686)


def shot(slot, hwnd: int):
    try:
        image = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", str(exc))
        return None
    slot._save(image, "latest.png")
    return image


def _click_ratio(slot, hwnd: int, point: tuple[float, float], label: str) -> bool:
    try:
        click_client_ratio(hwnd, point[0], point[1])
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return False
    slot._set("执行中", f"已点击「{label}」")
    return True


def activity_open(image) -> bool:
    hits = sorted(read_texts_in(image, *_ACTIVITY_TITLE), key=lambda hit: hit.x)
    return "活动" in "".join(compact(hit.text) for hit in hits)


def open_daily_list(slot, hwnd: int):
    """确认主界面，点活动，认标题，再点日常活动。失败时状态已经写好，返回空。"""
    image = shot(slot, hwnd)
    if image is None:
        return None
    for _ in range(3):
        if slot.stopped():
            return None
        if on_state_a(image):
            break
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None
        slot._set("执行中", "已按 Esc")
        time.sleep(0.5)
        image = shot(slot, hwnd)
        if image is None:
            return None
    if not on_state_a(image):
        slot._set("未知界面", "不在主界面")
        return None
    if not _click_ratio(slot, hwnd, _ACTIVITY_CLICK, "活动"):
        return None
    opened = False
    for _ in range(6):
        time.sleep(0.4)
        image = shot(slot, hwnd)
        if image is None:
            return None
        if activity_open(image):
            opened = True
            break
    if not opened:
        slot._set("未知界面", "活动弹窗没有打开")
        return None
    if not _click_ratio(slot, hwnd, _DAILY_CLICK, "日常活动"):
        return None
    time.sleep(0.4)
    return shot(slot, hwnd)
