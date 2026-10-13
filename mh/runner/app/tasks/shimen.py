"""师门。先认角色，再看活动列表右侧是「参加」还是「完成」。"""

import time

from app.daily import mark_done
from app.windows.capture import CaptureError
from app.windows.input import click_client_point, click_client_ratio, press_escape
from app.windows.ocr import TextHit, read_texts_in
from app.tasks.character import read_character
from app.toolkit.button import color_near, row_mark
from app.toolkit.dialog import escape_to_state_a
from app.toolkit.match import region_same, shimen_card
from app.toolkit.activity import SEARCH as _SEARCH
from app.toolkit.activity import open_daily_list
from app.toolkit.scroll import browse_list
from app.toolkit.screen import compact, hit_contains, label_right, on_state_a, row_button

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
    if image is not None:
        card = shimen_card(image)
        if card is not None:
            label, x, y, score = card
            return label, TextHit(label, score, x, y)
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


_DIALOG = ((0.210, 0.273, 0.252, 0.315), (236, 168, 115))
_ACTION = (0.296, 0.587, 0.903, 0.654)
_WELFARE_COLOR = ((0.132, 0.521, 0.264, 0.581), (220, 115, 53))
_WELFARE_TEXT = (0.455, 0.198, 0.554, 0.242)
_WELFARE_CLOSE = (0.9485, 0.225)
_STILL = (0.397, 0.576, 0.583, 0.766)
_DONE_COLOR = ((0.364, 0.351, 0.627, 0.424), (221, 164, 84))


def _shot(slot, hwnd: int):
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


def _wait(slot, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if slot.stopped():
            return False
        time.sleep(min(0.4, deadline - time.time()))
    return not slot.stopped()


def _is_main(image) -> bool:
    return on_state_a(image)


def _welfare(image) -> bool:
    box, expected = _WELFARE_COLOR
    if color_near(image, box, expected):
        return True
    texts = [compact(hit.text) for hit in read_texts_in(image, *_WELFARE_TEXT)]
    if any("福利" in text for text in texts):
        return True
    return "福" in texts and "利" in texts


def _find_card(slot, hwnd: int, _image):
    """先拖回列表头部，再逐页用图标找师门。"""
    return browse_list(slot, hwnd, _SEARCH, shimen_card)


def _back_main(slot, hwnd: int, image):
    for _ in range(4):
        if slot.stopped():
            return None
        if _is_main(image):
            return image
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None
        time.sleep(0.5)
        image = _shot(slot, hwnd)
        if image is None:
            return None
    if _is_main(image):
        return image
    slot._set("未知界面", "没有回到主界面")
    return None


def _action_hit(image) -> TextHit | None:
    found: TextHit | None = None
    for hit in read_texts_in(image, *_ACTION):
        text = compact(hit.text)
        if text not in ("去完成", "继续任务") and "去完成" not in text and "继续任务" not in text:
            continue
        if found is None or hit.score > found.score:
            found = hit
    return found


def run(slot, hwnd: int) -> None:
    """按测好的七步做师门。点下去完成或继续任务，并处理福利弹窗后停住。"""
    if not slot._character_id and not read_character(slot, hwnd, done=done_open, on_done=lambda: _mark(slot)):
        return
    image = open_daily_list(slot, hwnd)
    if image is None:
        return
    image, card = _find_card(slot, hwnd, image)
    if image is None:
        return
    if card is None:
        slot._set("未知界面", "活动列表里没有找到师门任务")
        return
    label, x, y, _score = card
    if label == "完成":
        _mark(slot)
        if _back_main(slot, hwnd, image) is None:
            return
        slot._running = True
        slot._set("执行中", "师门已完成，已回到主界面")
        return
    try:
        click_x, click_y = slot._client_point(hwnd, image, x, y)
        click_client_point(hwnd, click_x, click_y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return
    slot._set("执行中", "已点击「参加」")
    dialog = False
    box, expected = _DIALOG
    for _ in range(8):
        time.sleep(0.4)
        image = _shot(slot, hwnd)
        if image is None:
            return
        if color_near(image, box, expected):
            dialog = True
            break
    if not dialog:
        slot._set("未知界面", "师门弹窗没有打开")
        return
    action = _action_hit(image)
    if action is None:
        slot._set("未知界面", "师门弹窗里没有「去完成」或「继续任务」")
        return
    action_label = "继续任务" if "继续任务" in compact(action.text) else "去完成"
    try:
        click_x, click_y = slot._client_point(hwnd, image, action.x, action.y)
        click_client_point(hwnd, click_x, click_y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return
    slot._set("执行中", f"已点击「{action_label}」")
    time.sleep(1.2)
    image = _shot(slot, hwnd)
    if image is None:
        return
    if _welfare(image):
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return
        time.sleep(0.5)
        image = _shot(slot, hwnd)
        if image is None:
            return
        if _welfare(image):
            if not _click_ratio(slot, hwnd, _WELFARE_CLOSE, "关闭福利"):
                return
            time.sleep(0.5)
            image = _shot(slot, hwnd)
            if image is None:
                return
            if _welfare(image):
                slot._set("未知界面", "福利窗口没有关掉")
                return
    _watch_shimen(slot, hwnd, image)


def _watch_shimen(slot, hwnd: int, previous) -> None:
    """每 20 秒看中下这块。没变时，完成色对上就回主界面，否则按一次 Esc 继续。"""
    while True:
        slot._set("执行中", "师门进行中")
        if not _wait(slot, 20):
            return
        image = _shot(slot, hwnd)
        if image is None:
            return
        if not region_same(previous, image, _STILL):
            previous = image
            continue
        box, expected = _DONE_COLOR
        if color_near(image, box, expected):
            _mark(slot)
            for _ in range(2):
                if slot.stopped():
                    return
                try:
                    press_escape(hwnd)
                except OSError as exc:
                    slot._set("未知界面", str(exc))
                    return
                time.sleep(0.5)
            image = _shot(slot, hwnd)
            if image is None:
                return
            if _is_main(image):
                slot._running = True
                slot._set("执行中", "师门已完成，已回到主界面")
                return
            slot._set("未知界面", "师门已完成，按了两次 Esc 还没回到主界面")
            return
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return
        slot._set("执行中", "画面没变，已按一次 Esc")
        time.sleep(0.5)
        image = _shot(slot, hwnd)
        if image is None:
            return
        previous = image
