"""师门。先认角色，再看活动列表右侧是「参加」还是「完成」。"""

import time

from app.daily import mark_done
from app.windows.capture import CaptureError
from app.windows.input import click_client_point
from app.windows.ocr import TextHit, read_texts, read_texts_in
from app.tasks.character import read_character
from app.toolkit.button import row_mark
from app.toolkit.click import open_activity_list, wait_until_still
from app.toolkit.dialog import escape_to_state_a, watch_center
from app.toolkit.scroll import ListScroll
from app.toolkit.screen import auto_pathing, compact, hit_contains, is_state_a, label_right, row_button, welfare_open

TASK = "师门"


def done_open(hits: list[TextHit], image_height: int, image=None) -> bool:
    """「师门任务完成」只认画面上半部，避免聊天里的字凑成这一句。"""
    if image is not None:
        hits = read_texts_in(image, 0.28, 0.14, 0.72, 0.50)
        image_height = image.height
    return any(
        "师门" in compact(hit.text) and "完成" in compact(hit.text) and hit.y < image_height * 0.55
        for hit in hits
    )


def _panel_action(hits: list[TextHit]) -> TextHit | None:
    texts = [compact(hit.text) for hit in hits]
    on_panel = any(
        text == "寻趣" or text == "师门" or "自动选择每日任务" in text or "自动完成任务" in text
        for text in texts
    )
    if not on_panel:
        return None
    continued = hit_contains(hits, "继续任务")
    if continued is not None:
        return continued
    return hit_contains(hits, "去完成")


def _row(hits: list[TextHit], width: int, image=None) -> tuple[str, TextHit] | None:
    """活动列表里「师门任务」右侧是「参加」还是「完成」。不看右侧任务追踪。"""
    daily = hit_contains(hits, "日常活动")
    best: tuple[str, TextHit, float] | None = None
    for hit in hits:
        if "师门任务" not in compact(hit.text) or hit.x > width * 0.80:
            continue
        if daily is not None and hit.x < daily.x + 80:
            continue
        local = row_button(image, hit, ("完成", "参加")) if image is not None else None
        finished = local if local is not None and compact(local.text) == "完成" else label_right(hits, hit, "完成", skip_contains="师门")
        join = local if local is not None and compact(local.text) == "参加" else label_right(hits, hit, "参加", skip_contains="师门")
        if finished is not None:
            chosen = ("完成", finished)
        elif join is not None:
            chosen = ("参加", join)
        elif image is not None and (mark := row_mark(image, hit)) is not None:
            chosen = (mark, TextHit(mark, hit.score, hit.x + 160, hit.y + 20))
        else:
            chosen = None
        if chosen is None:
            continue
        if best is None or hit.score > best[2]:
            best = (chosen[0], chosen[1], hit.score)
    if best is None:
        return None
    return best[0], best[1]


def _mark(slot) -> None:
    mark_done(slot._character_id, TASK)


def _finish(slot, hwnd: int, image) -> bool:
    """看到完成就记下并回到状态 A。回不去时返回假，调用方应停住。"""
    _mark(slot)
    image, _seen = escape_to_state_a(slot, hwnd, image, done=done_open, task=TASK)
    if image is None:
        return False
    slot._running = True
    slot._set("执行中", "已按 Esc 回到主界面，师门完成")
    return True


def run(slot, hwnd: int) -> None:
    """先记下角色，再看活动列表里师门是「参加」还是「完成」。"""
    if not read_character(slot, hwnd, done=done_open, on_done=lambda: _mark(slot)):
        return
    deadline = time.time() + 50
    opened_daily = False
    listing = ListScroll("师门任务")
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
        if done_open(hits, image.height, image):
            _finish(slot, hwnd, image)
            return
        if auto_pathing(hits, image.width, image.height):
            watch_center(slot, hwnd, "自动寻路", done_open, lambda: _mark(slot), task=TASK)
            return
        if welfare_open(hits, image.width, image.height):
            image, seen_done = escape_to_state_a(slot, hwnd, image, done=done_open, task=TASK)
            if image is None:
                return
            if seen_done:
                _mark(slot)
                slot._running = True
                slot._set("执行中", "已按 Esc 回到主界面，师门完成")
                return
            continue
        action = _panel_action(hits)
        if action is not None:
            label = "继续任务" if "继续任务" in compact(action.text) else "去完成"
            x, y = slot._client_point(hwnd, image, action.x, action.y)
            try:
                click_client_point(hwnd, x, y)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return
            slot._set("执行中", f"已点击「{label}」，师门开始自动进行")
            watch_center(slot, hwnd, label, done_open, lambda: _mark(slot), task=TASK)
            return
        row = _row(hits, image.width, image)
        daily = hit_contains(hits, "日常活动")
        if row is not None and opened_daily:
            kind, listed = row
            if kind == "完成":
                _mark(slot)
                image, _seen = escape_to_state_a(slot, hwnd, image, done=done_open, task=TASK)
                if image is None:
                    return
                slot._running = True
                slot._set("执行中", "活动列表里「师门任务」右侧是「完成」，今日不再做")
                return
            list_clicks += 1
            if list_clicks > 3:
                slot._set("未知界面", "点了「参加」，师门面板没有打开")
                return
            x, y = slot._client_point(hwnd, image, listed.x, listed.y)
            try:
                click_client_point(hwnd, x, y)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return
            slot._set("执行中", "已点击「师门任务」右侧的「参加」")
            image = wait_until_still(slot, hwnd, image)
            if image is None:
                return
            continue
        elif daily is not None and not opened_daily:
            x, y = slot._client_point(hwnd, image, daily.x, daily.y)
            try:
                click_client_point(hwnd, x, y)
            except OSError as exc:
                slot._set("未知界面", str(exc))
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
                slot._set("未知界面", "活动列表里没有找到「师门任务」")
                return
            continue
        else:
            if not is_state_a(hits, image.width, image.height, image):
                image, seen_done = escape_to_state_a(slot, hwnd, image, done=done_open, task=TASK)
                if image is None:
                    return
                if seen_done:
                    _mark(slot)
                    slot._running = True
                    slot._set("执行中", "已按 Esc 回到主界面，师门完成")
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
    hits = read_texts(image)
    row = _row(hits, image.width, image)
    if row is not None and row[0] == "完成":
        _mark(slot)
        image, _seen = escape_to_state_a(slot, hwnd, image, done=done_open, task=TASK)
        if image is None:
            return
        slot._running = True
        slot._set("执行中", "活动列表里「师门任务」右侧是「完成」，今日不再做")
        return
    slot._set("未知界面", "没有把师门任务点开")
