"""宝图。活动列表的参加、完成、继续任务和师门一样，点开后等对话再点「听听无妨」。"""

import time

from app.daily import mark_done
from app.windows.capture import CaptureError
from app.windows.input import click_client_point, click_client_ratio, client_size, press_escape, scroll_client_point
from app.toolkit.button import row_mark
from app.toolkit.click import open_activity_list, wait_until_still
from app.toolkit.dialog import escape_to_state_a
from app.toolkit.scroll import ListScroll
from app.windows.ocr import TextHit, read_texts
from app.tasks.character import read_character
from app.toolkit.screen import auto_pathing, center_still, compact, hit_contains, in_battle, is_state_a, label_right, row_button, welfare_open

TASK = "宝图"
# 主界面右侧「任务」页签。文字中心约在客户区 0.840, 0.201。
_TASK_TAB = (0.840, 0.201)
_TRACKER_SCROLL = (0.860, 0.420)


def _row(hits: list[TextHit], width: int, image=None) -> tuple[str, TextHit] | None:
    """活动列表里「宝图任务」右侧是「完成」「继续任务」还是「参加」。不看右侧任务追踪。"""
    daily = hit_contains(hits, "日常活动")
    best: tuple[str, TextHit, float] | None = None
    for hit in hits:
        text = compact(hit.text)
        if "宝图任务" not in text or hit.x > width * 0.80:
            continue
        if daily is not None and hit.x < daily.x + 80:
            continue
        local = row_button(image, hit, ("完成", "继续任务", "参加")) if image is not None else None
        finished = local if local is not None and compact(local.text) == "完成" else label_right(hits, hit, "完成", skip_contains="宝图")
        resume = local if local is not None and compact(local.text) == "继续任务" else label_right(hits, hit, "继续任务", skip_contains="宝图")
        join = local if local is not None and compact(local.text) == "参加" else label_right(hits, hit, "参加", skip_contains="宝图")
        if finished is not None:
            chosen = ("完成", finished)
        elif resume is not None:
            chosen = ("继续任务", resume)
        elif join is not None:
            chosen = ("参加", join)
        elif image is not None and (mark := row_mark(image, hit)) is not None:
            chosen = (mark, TextHit(mark, hit.score, hit.x + 160, hit.y + 20))
        else:
            continue
        if best is None or hit.score > best[2]:
            best = (chosen[0], chosen[1], hit.score)
    if best is None:
        return None
    return best[0], best[1]


def _listen(hits: list[TextHit], height: int) -> TextHit | None:
    best: TextHit | None = None
    for hit in hits:
        if "听听无妨" not in compact(hit.text):
            continue
        if not height * 0.25 < hit.y < height * 0.80:
            continue
        if best is None or hit.score > best.score:
            best = hit
    return best


def _resume_button(hits: list[TextHit], height: int) -> TextHit | None:
    """参加之后弹出的「继续任务」或「去完成」。"""
    for label in ("继续任务", "去完成"):
        found = hit_contains(hits, label)
        if found is None or compact(found.text) != label:
            continue
        if height * 0.25 < found.y < height * 0.80:
            return found
    return None


def _tracker_hit(hits: list[TextHit], width: int) -> bool:
    return any("宝图任务" in compact(hit.text) and hit.x > width * 0.75 for hit in hits)


def _task_tab(hits: list[TextHit], width: int, height: int) -> TextHit | None:
    best: TextHit | None = None
    for hit in hits:
        if compact(hit.text) != "任务":
            continue
        if hit.x < width * 0.75 or hit.y > height * 0.30:
            continue
        if best is None or hit.score > best.score:
            best = hit
    return best


def _mark(slot) -> None:
    mark_done(slot._character_id, TASK)


def _click_hit(slot, hwnd: int, image, hit: TextHit) -> bool:
    x, y = slot._client_point(hwnd, image, hit.x, hit.y)
    try:
        click_client_point(hwnd, x, y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return False
    return True


def _click_task_tab(slot, hwnd: int, image, hits: list[TextHit]) -> bool:
    tab = _task_tab(hits, image.width, image.height)
    if tab is not None:
        return _click_hit(slot, hwnd, image, tab)
    try:
        click_client_ratio(hwnd, _TASK_TAB[0], _TASK_TAB[1])
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return False
    return True


def _tracker_has_baotu(slot, hwnd: int) -> bool | None:
    """状态 A 下看右侧任务栏。没有「宝图任务」时点「任务」并翻一下列表。"""
    image = slot._grab(hwnd)
    if image is None:
        return None
    hits = read_texts(image)
    if in_battle(hits, image.width, image.height, image):
        return True
    if not is_state_a(hits, image.width, image.height, image):
        return False
    if _tracker_hit(hits, image.width):
        return True
    if not _click_task_tab(slot, hwnd, image, hits):
        return None
    time.sleep(0.4)
    image = slot._grab(hwnd)
    if image is None:
        return None
    if _tracker_hit(read_texts(image), image.width):
        return True
    try:
        width, height = client_size(hwnd)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return None
    scroll_x = int(round((width - 1) * _TRACKER_SCROLL[0]))
    scroll_y = int(round((height - 1) * _TRACKER_SCROLL[1]))
    for notches in (-2, -2, -2, 2, 2, 2):
        try:
            scroll_client_point(hwnd, scroll_x, scroll_y, notches)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None
        time.sleep(0.35)
        image = slot._grab(hwnd)
        if image is None:
            return None
        if _tracker_hit(read_texts(image), image.width):
            return True
    return False


def _wait_listen(slot, hwnd: int) -> bool:
    """参加或继续任务之后，走到店小二并点「听听无妨」。"""
    deadline = time.time() + 25
    clicked_panel = False
    slot._set("执行中", "已点开宝图，等待对话")
    while time.time() < deadline:
        if slot.stopped():
            return False
        image = slot._grab(hwnd)
        if image is None:
            return False
        hits = read_texts(image)
        if in_battle(hits, image.width, image.height, image):
            return True
        listen = _listen(hits, image.height)
        if listen is not None:
            if not _click_hit(slot, hwnd, image, listen):
                return False
            slot._set("执行中", "已点击「听听无妨」，宝图开始自动进行")
            return True
        if not clicked_panel:
            extra = _resume_button(hits, image.height)
            if extra is not None:
                label = compact(extra.text)
                if not _click_hit(slot, hwnd, image, extra):
                    return False
                clicked_panel = True
                slot._set("执行中", f"已点击「{label}」")
        time.sleep(1)
    slot._set("未知界面", "点了宝图，没有看到「听听无妨」")
    return False


def _watch(slot, hwnd: int) -> None:
    """宝图自动进行。战斗页不按 Esc。状态 A 时看任务栏里还有没有「宝图任务」。"""
    deadline = time.time() + 25 * 60
    held = None
    misses = 0
    slot._set("执行中", "宝图进行中")
    while time.time() < deadline:
        if slot.stopped():
            return
        time.sleep(15)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return
        slot._save(image, "latest.png")
        hits = read_texts(image)
        if in_battle(hits, image.width, image.height, image):
            held = None
            misses = 0
            slot._set("执行中", "宝图战斗中")
            continue
        if auto_pathing(hits, image.width, image.height):
            held = None
            misses = 0
            slot._set("执行中", "宝图自动寻路中")
            continue
        if is_state_a(hits, image.width, image.height, image):
            held = None
            found = _tracker_has_baotu(slot, hwnd)
            if found is None:
                return
            if found:
                misses = 0
                slot._set("执行中", "宝图进行中，任务栏能看到宝图任务")
                continue
            misses += 1
            if misses < 2:
                slot._set("执行中", "宝图进行中，任务栏这次没看到宝图任务")
                continue
            if _finish_from_list(slot, hwnd):
                return
            misses = 0
            continue
        if held is not None and center_still(held, image):
            held = None
            try:
                press_escape(hwnd)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return
            slot._set("执行中", "弹窗停在画面中心，已按 Esc")
            continue
        if held is None:
            slot._set("执行中", "宝图进行中，15 秒后再看画面中心")
        else:
            slot._set("执行中", "宝图进行中，中心画面有变化，先不关")
        held = image
    slot._running = True
    slot._set("执行中", "宝图进行中，还没在活动列表里看到「完成」")


def _finish_from_list(slot, hwnd: int) -> bool:
    """任务栏连续两次没有宝图时，打开活动列表核对。看到「完成」才记下来。"""
    deadline = time.time() + 40
    opened_daily = False
    listing = ListScroll("宝图任务")
    try:
        image = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", str(exc))
        return True
    slot._save(image, "latest.png")
    while time.time() < deadline:
        if slot.stopped():
            return True
        hits = read_texts(image)
        if in_battle(hits, image.width, image.height, image):
            return False
        row = _row(hits, image.width, image)
        daily = hit_contains(hits, "日常活动")
        if row is not None and opened_daily:
            kind, _listed = row
            image, _seen = escape_to_state_a(slot, hwnd, image, task=TASK, hold=in_battle)
            if image is None:
                return True
            if kind == "完成":
                _mark(slot)
                slot._running = True
                slot._set("执行中", "活动列表里「宝图任务」右侧是「完成」，今日不再做")
                return True
            slot._running = True
            slot._set("执行中", f"任务栏没有宝图任务，活动列表右侧是「{kind}」，先不重复点")
            return False
        if daily is not None and not opened_daily:
            if not _click_hit(slot, hwnd, image, daily):
                return True
            opened_daily = True
            image = wait_until_still(slot, hwnd, image)
            if image is None:
                return True
            continue
        elif daily is not None:
            image, exhausted = listing.step(slot, hwnd, image)
            if image is None:
                return True
            if exhausted:
                slot._set("执行中", "活动列表里没有找到「宝图任务」")
                return False
            continue
        elif not is_state_a(hits, image.width, image.height, image):
            image, _seen = escape_to_state_a(slot, hwnd, image, task=TASK, hold=in_battle)
            if image is None:
                return True
            continue
        else:
            image = open_activity_list(slot, hwnd, image)
            if image is None:
                return False
            continue
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return True
        slot._save(image, "latest.png")
    return False


def run(slot, hwnd: int) -> None:
    """师门结束后看宝图。已经在战斗里就只守着，不点活动。"""
    if not slot._character_id:
        if not read_character(slot, hwnd):
            return
    deadline = time.time() + 50
    opened_daily = False
    listing = ListScroll("宝图任务")
    list_clicks = 0
    try:
        image = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", str(exc))
        return
    slot._save(image, "latest.png")
    while time.time() < deadline:
        if slot.stopped():
            return
        hits = read_texts(image)
        if in_battle(hits, image.width, image.height, image):
            _watch(slot, hwnd)
            return
        if auto_pathing(hits, image.width, image.height):
            slot._set("执行中", "宝图自动寻路中")
            _watch(slot, hwnd)
            return
        listen = _listen(hits, image.height)
        if listen is not None:
            if not _click_hit(slot, hwnd, image, listen):
                return
            slot._set("执行中", "已点击「听听无妨」，宝图开始自动进行")
            _watch(slot, hwnd)
            return
        if welfare_open(hits, image.width, image.height):
            image, _seen = escape_to_state_a(slot, hwnd, image, task=TASK, hold=in_battle)
            if image is None:
                return
            continue
        row = _row(hits, image.width, image)
        daily = hit_contains(hits, "日常活动")
        if row is not None and opened_daily:
            kind, listed = row
            if kind == "完成":
                _mark(slot)
                image, _seen = escape_to_state_a(slot, hwnd, image, task=TASK, hold=in_battle)
                if image is None:
                    return
                slot._running = True
                slot._set("执行中", "活动列表里「宝图任务」右侧是「完成」，今日不再做")
                return
            list_clicks += 1
            if list_clicks > 3:
                slot._set("未知界面", f"点了「{kind}」，宝图没有开始")
                return
            if not _click_hit(slot, hwnd, image, listed):
                return
            slot._set("执行中", f"已点击「宝图任务」右侧的「{kind}」")
            image = wait_until_still(slot, hwnd, image)
            if image is None:
                return
            if _wait_listen(slot, hwnd):
                _watch(slot, hwnd)
            return
        elif daily is not None and not opened_daily:
            if not _click_hit(slot, hwnd, image, daily):
                return
            opened_daily = True
            slot._set("执行中", "已点击「日常活动」")
            image = wait_until_still(slot, hwnd, image)
            if image is None:
                return
            continue
        elif daily is not None:
            image, exhausted = listing.step(slot, hwnd, image)
            if image is None:
                return
            if exhausted:
                slot._set("未知界面", "活动列表里没有找到「宝图任务」")
                return
            continue
        else:
            if not is_state_a(hits, image.width, image.height, image):
                image, _seen = escape_to_state_a(slot, hwnd, image, task=TASK, hold=in_battle)
                if image is None:
                    return
                continue
            image = open_activity_list(slot, hwnd, image)
            if image is None:
                return
            continue
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return
        slot._save(image, "latest.png")
    slot._set("未知界面", "没有把宝图任务点开")
