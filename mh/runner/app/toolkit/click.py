"""点一个按钮，等到下一屏的检查点出现才算点中。"""

import time

from PIL import Image

from app.windows.capture import CaptureError
from app.windows.input import click_client_ratio
from app.windows.ocr import read_texts
from app.toolkit.screen import center_still, compact, is_state_a


def wait_until_still(slot, hwnd: int, image: Image.Image, timeout: float = 1.8) -> Image.Image | None:
    """点完之后等到画面中心停住，再拿这张图去认。超时就用最后一张。"""
    deadline = time.time() + timeout
    previous = image
    while time.time() < deadline:
        if slot.stopped():
            return None
        time.sleep(0.35)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return None
        slot._save(image, "latest.png")
        if center_still(previous, image):
            return image
        previous = image
    return image


def activity_list_open(hits) -> bool:
    """活动列表已经打开：能看到「日常活动」或「挑战活动」。"""
    for hit in hits:
        text = compact(hit.text)
        if "日常活动" in text or "挑战活动" in text:
            return True
    return False


def open_activity_list(slot, hwnd: int, image: Image.Image, timeout: float = 8.0) -> Image.Image | None:
    """点「活动」，直到活动列表出现。中间隔开再点，不连点。"""
    deadline = time.time() + timeout
    clicks = 0
    last_click = 0.0
    while time.time() < deadline:
        if slot.stopped():
            return None
        hits = read_texts(image)
        if activity_list_open(hits):
            return image
        now = time.time()
        ready = is_state_a(hits, image.width, image.height, image)
        if clicks >= 3 and not ready:
            break
        if clicks < 3 and ready and now - last_click >= 1.2:
            point = slot.spec.activity_button
            try:
                x, y = click_client_ratio(hwnd, point.x, point.y)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return None
            clicks += 1
            last_click = now
            slot._set("执行中", f"已点击「活动」({x}, {y})")
            image = wait_until_still(slot, hwnd, image)
            if image is None:
                return None
            continue
        time.sleep(0.45)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return None
        slot._save(image, "latest.png")
    slot._set("未知界面", "已点击「活动」，活动列表没有打开")
    return None
