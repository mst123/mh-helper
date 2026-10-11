"""列表滚动。先滚回头部，再往下翻。活动列表用这套，以后别的长列表也可以用。"""

import re
import time

from PIL import Image

from app.windows.capture import CaptureError
from app.windows.input import client_size, scroll_client_point, scroll_real
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
