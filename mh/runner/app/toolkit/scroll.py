"""列表翻页。滚轮仍留给账号列表。活动列表在给定范围里按下缓慢拖动。"""

import re
import time
from collections.abc import Callable

from PIL import Image

from app.windows.capture import CaptureError
from app.windows.input import client_size, drag_real, scroll_client_point, scroll_real
from app.windows.ocr import read_texts


def _list_names(image: Image.Image) -> set[str]:
    """活动列表中间那一块的文字。用来判断这一页有没有翻动。"""
    names: set[str] = set()
    for hit in read_texts(image):
        if not image.height * 0.20 < hit.y < image.height * 0.80:
            continue
        if not image.width * 0.28 < hit.x < image.width * 0.72:
            continue
        text = re.sub(r"\s+", "", hit.text)
        if len(text) >= 2:
            names.add(text)
    return names


def _same_page(before: set[str], after: set[str]) -> bool:
    if len(before) < 3 or len(after) < 3:
        return False
    overlap = len(before & after) / max(len(before), len(after))
    return overlap >= 0.7


def page_activity_list(slot, hwnd: int, image: Image.Image, notches: int = -9):
    """翻一页。notches 为负向下，为正向头。一次默认 9 格。窗口消息翻不动时改用真实滚轮。

    第二个返回值表示列表文字没有变化，这一头已经翻不动了。
    """
    before = _list_names(image)
    width, height = client_size(hwnd)
    x = int(round((width - 1) * 0.62))
    y = int(round((height - 1) * 0.45))
    scroll_client_point(hwnd, x, y, notches)
    time.sleep(0.4)
    try:
        moved = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", str(exc))
        return None, False
    slot._save(moved, "latest.png")
    if not _same_page(before, _list_names(moved)):
        return moved, False
    scroll_real(hwnd, x, y, notches)
    time.sleep(0.4)
    try:
        moved = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", str(exc))
        return None, False
    slot._save(moved, "latest.png")
    return moved, _same_page(before, _list_names(moved))


class ListScroll:
    """打开列表后先滚回头部，再持续往下找。列表不一定停在头部。"""

    def __init__(self, task_name: str) -> None:
        self.task_name = task_name
        self.scrolled = 0
        self.at_top = False
        self.at_bottom = False

    def step(self, slot, hwnd: int, image: Image.Image) -> tuple[Image.Image | None, bool]:
        """翻一页。返回新图，以及是否已经从头部翻到底还没找到。失败时新图是 None。"""
        if not self.at_top:
            if self.scrolled >= 16:
                self.at_top = True
                self.scrolled = 0
                return image, False
            try:
                image, reached = page_activity_list(slot, hwnd, image, notches=9)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return None, False
            if image is None:
                return None, False
            self.scrolled += 1
            if reached:
                self.at_top = True
                self.scrolled = 0
            slot._set("执行中", "正在把活动列表滚回头部")
            return image, False
        if self.at_bottom or self.scrolled >= 16:
            return image, True
        try:
            image, self.at_bottom = page_activity_list(slot, hwnd, image)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None, False
        if image is None:
            return None, False
        self.scrolled += 1
        slot._set("执行中", f"正在往下翻活动列表查找「{self.task_name}」")
        return image, False


def drag_in_box(
    hwnd: int,
    box: tuple[float, float, float, float],
    toward: str,
    distance: int,
    seconds: float,
) -> None:
    """在比例框内按下并拖动。toward 为 head 时鼠标向下，列表回到更靠前的条目。toward 为 tail 时鼠标向上。"""
    width, height = client_size(hwnd)
    left = int(box[0] * width)
    top = int(box[1] * height)
    right = max(left + 1, int(box[2] * width))
    bottom = max(top + 1, int(box[3] * height))
    pad = 12
    room = (bottom - top) - pad * 2
    if room < 20 or right - left < pad * 2:
        raise OSError("列表区域太小，拖不动")
    travel = min(int(distance), room)
    x = max(left + pad, min(right - pad, (left + right) // 2))
    if toward == "head":
        y = top + pad
        dy = travel
    elif toward == "tail":
        y = bottom - pad
        dy = -travel
    else:
        raise OSError("拖动方向无效")
    drag_real(hwnd, x, y, 0, dy, seconds)


def _grab(slot, hwnd: int):
    try:
        image = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", str(exc))
        return None
    slot._save(image, "latest.png")
    return image


def browse_list(
    slot,
    hwnd: int,
    box: tuple[float, float, float, float],
    look: Callable[[Image.Image], object],
    distance: int = 250,
    page_seconds: float = 1.0,
    head_seconds: float = 0.3,
    nudge: int = 100,
):
    """先向下快拖两次回到头部，再向上按页查看。每页交给 look。都没有再向上挪一截。

    返回 (截图, look 的结果)。截图失败或中途停下时截图是 None。
    """
    try:
        for _ in range(2):
            if slot.stopped():
                return None, None
            slot._set("执行中", "正在把列表拖回头部")
            drag_in_box(hwnd, box, "head", distance, head_seconds)
            time.sleep(0.12)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return None, None
    time.sleep(0.2)
    image = _grab(slot, hwnd)
    if image is None:
        return None, None
    found = look(image)
    if found is not None:
        return image, found
    for _ in range(2):
        if slot.stopped():
            return None, None
        try:
            slot._set("执行中", "正在向下翻列表")
            drag_in_box(hwnd, box, "tail", distance, page_seconds)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None, None
        time.sleep(0.2)
        image = _grab(slot, hwnd)
        if image is None:
            return None, None
        found = look(image)
        if found is not None:
            return image, found
    if slot.stopped():
        return None, None
    try:
        slot._set("执行中", "再挪一截查看")
        drag_in_box(hwnd, box, "tail", nudge, max(0.2, page_seconds * nudge / max(distance, 1)))
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return None, None
    time.sleep(0.2)
    image = _grab(slot, hwnd)
    if image is None:
        return None, None
    return image, look(image)
