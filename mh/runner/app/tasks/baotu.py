"""宝图。前半段和师门一样。点参加后先看主界面是不是已经出现「宝图任务」。"""

import time

from app.daily import mark_done
from app.windows.input import click_client_point, click_client_ratio, press_escape
from app.windows.ocr import read_texts_in
from app.tasks.character import read_character
from app.toolkit.activity import SEARCH, activity_open, open_daily_list, shot
from app.toolkit.match import find_pictures, icon_card, load_picture, region_same
from app.toolkit.screen import compact, on_state_a
from app.toolkit.scroll import browse_list

TASK = "宝图"
_WAITER_BOX = (0.057, 0.720, 0.277, 0.948)
_TALK_CLICK = (0.8325, 0.507)
_NUT_BOX = (0.910, 0.864, 0.999, 0.977)
_TASK_BOX = (0.787, 0.255, 0.877, 0.299)
_STILL = (0.397, 0.576, 0.583, 0.766)
_LOOK_SECONDS = 15
_POPUP_SECONDS = 10
_SETTLE_SECONDS = 3
_ICON = None
_WAITER = None
_NUT = None


def _icon():
    global _ICON
    if _ICON is None:
        _ICON = load_picture("宝图任务.png")
    return _ICON


def _waiter():
    global _WAITER
    if _WAITER is None:
        _WAITER = load_picture("店小二.png")
    return _WAITER


def _nut():
    global _NUT
    if _NUT is None:
        _NUT = load_picture("自动战斗螺母.png")
    return _NUT


def _look(image):
    return icon_card(image, _icon())


def _waiter_open(image) -> bool:
    return _crop_has(image, _WAITER_BOX, _waiter())


def _back_main(slot, hwnd: int, image):
    for _ in range(4):
        if slot.stopped():
            return None
        if on_state_a(image):
            return image
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None
        time.sleep(0.5)
        image = shot(slot, hwnd)
        if image is None:
            return None
    if on_state_a(image):
        return image
    slot._set("未知界面", "没有回到主界面")
    return None


def _wait(slot, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if slot.stopped():
            return False
        time.sleep(min(0.4, deadline - time.time()))
    return not slot.stopped()


def _crop_has(image, box: tuple[float, float, float, float], picture) -> bool:
    width, height = image.size
    left = int(box[0] * width)
    top = int(box[1] * height)
    right = max(left + 1, int(box[2] * width))
    bottom = max(top + 1, int(box[3] * height))
    return bool(find_pictures(image.crop((left, top, right, bottom)), picture, threshold=0.85, limit=1))


def _task_name(image) -> str:
    hits = sorted(read_texts_in(image, *_TASK_BOX), key=lambda hit: hit.x)
    return compact("".join(hit.text for hit in hits))


def _auto_started(slot, hwnd: int) -> bool | None:
    """活动列表关掉之后，主界面任务名是「宝图任务」就表示已经自动开始。最多等 3 秒。"""
    deadline = time.time() + _SETTLE_SECONDS
    while True:
        if slot.stopped():
            return None
        image = shot(slot, hwnd)
        if image is None:
            return None
        if not activity_open(image) and _task_name(image) == "宝图任务":
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.4)


def _watch(slot, hwnd: int) -> None:
    """进入自动打宝图后：战斗或主界面上仍是宝图任务就隔 15 秒再看。两边都不是就隔 10 秒看无关弹窗。"""
    slot._set("执行中", "进入自动打宝图")
    if not _wait(slot, _LOOK_SECONDS):
        return
    while not slot.stopped():
        image = shot(slot, hwnd)
        if image is None:
            return
        if _crop_has(image, _NUT_BOX, _nut()):
            slot._set("执行中", "自动战斗中")
            if not _wait(slot, _LOOK_SECONDS):
                return
            continue
        if on_state_a(image):
            if _task_name(image) == "宝图任务":
                slot._set("执行中", "主界面仍是宝图任务")
                if not _wait(slot, _LOOK_SECONDS):
                    return
                continue
            mark_done(slot._character_id, TASK)
            slot._running = True
            slot._set("执行中", "宝图已完成，已回到主界面")
            return
        previous = image
        slot._set("执行中", "不在战斗也不在主界面")
        if not _wait(slot, _POPUP_SECONDS):
            return
        image = shot(slot, hwnd)
        if image is None:
            return
        if not region_same(previous, image, _STILL):
            continue
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return
        slot._set("执行中", "已按 Esc 关闭弹窗")
        time.sleep(0.5)


def _click_join(slot, hwnd: int, image, x: int, y: int) -> bool:
    try:
        click_x, click_y = slot._client_point(hwnd, image, x, y)
        click_client_point(hwnd, click_x, click_y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return False
    slot._set("执行中", "已点击「参加」")
    return True


def run(slot, hwnd: int) -> None:
    """打开日常活动，找到宝图。完成就回主界面。点参加后先认「宝图任务」，没有再点店小二。"""
    if not slot._character_id and not read_character(slot, hwnd):
        return
    image = open_daily_list(slot, hwnd)
    if image is None:
        return
    image, card = browse_list(slot, hwnd, SEARCH, _look)
    if image is None:
        return
    if card is None:
        slot._set("未知界面", "活动列表里没有找到宝图任务")
        return
    label, x, y, _score, _hit = card
    if label == "完成":
        mark_done(slot._character_id, TASK)
        if _back_main(slot, hwnd, image) is None:
            return
        slot._running = True
        slot._set("执行中", "宝图已完成，已回到主界面")
        return
    if not _click_join(slot, hwnd, image, x, y):
        return
    slot._running = True
    started = _auto_started(slot, hwnd)
    if started is None:
        return
    if started:
        _watch(slot, hwnd)
        return
    image = shot(slot, hwnd)
    if image is None:
        return
    if not _waiter_open(image):
        slot._set("未知界面", "没有看到店小二")
        return
    try:
        click_client_ratio(hwnd, _TALK_CLICK[0], _TALK_CLICK[1])
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return
    slot._running = True
    _watch(slot, hwnd)
