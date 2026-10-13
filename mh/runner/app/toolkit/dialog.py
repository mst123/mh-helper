"""关弹窗。按 Esc 回到状态 A，以及任务进行中每 15 秒看一次画面中心。"""

import time

from PIL import Image

from app.windows.capture import CaptureError
from app.windows.input import press_escape
from app.windows.ocr import read_texts
from app.toolkit.screen import auto_pathing, center_still, in_battle, is_state_a, on_state_a


def escape_to_state_a(slot, hwnd: int, image: Image.Image, done=None, task: str = "师门", limit: int = 8, hold=None):
    """按 Esc 关掉当前弹窗，直到状态 A。done 认出任务完成时，返回值里的标记为真。

    hold 为真时停手，例如战斗页不能按 Esc。
    """
    seen_done = False
    phrase = f"{task}完成"
    for _ in range(limit):
        if slot.stopped():
            return None, seen_done
        if on_state_a(image):
            return image, seen_done
        hits = read_texts(image)
        if done is not None and done(hits, image.height, image):
            seen_done = True
        if is_state_a(hits, image.width, image.height, image):
            return image, seen_done
        if hold is not None and hold(hits, image.width, image.height):
            return image, seen_done
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None, seen_done
        if seen_done:
            slot._set("执行中", f"已看到{phrase}，正在按 Esc 回到主界面")
        else:
            slot._set("执行中", "已按 Esc 关闭弹窗")
        time.sleep(0.6)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return None, seen_done
        slot._save(image, "latest.png")
    if on_state_a(image):
        return image, seen_done
    hits = read_texts(image)
    if done is not None and done(hits, image.height, image):
        seen_done = True
    if is_state_a(hits, image.width, image.height, image):
        return image, seen_done
    if hold is not None and hold(hits, image.width, image.height):
        return image, seen_done
    if seen_done:
        slot._set("未知界面", f"已看到{phrase}，按了 Esc，没有回到主界面")
    else:
        slot._set("未知界面", "按了 Esc，没有回到主界面")
    return None, seen_done


def watch_center(slot, hwnd: int, label: str, done, on_done, task: str = "师门") -> None:
    """任务自动进行时，每 15 秒看画面中心。连续两次几乎不变，才按一次 Esc。"""
    deadline = time.time() + 20 * 60
    seen_done = False
    escapes = 0
    held: Image.Image | None = None
    phrase = f"{task}完成"
    slot._set("执行中", f"已点击「{label}」，{task}进行中")
    while time.time() < deadline:
        if slot.stopped():
            return
        time.sleep(0.7 if seen_done else 15)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return
        slot._save(image, "latest.png")
        hits = read_texts(image)
        if done(hits, image.height, image):
            if not seen_done:
                on_done()
            seen_done = True
        if seen_done:
            held = None
            if is_state_a(hits, image.width, image.height, image):
                on_done()
                slot._running = True
                slot._set("执行中", f"已按 Esc 回到主界面，{phrase}")
                return
            escapes += 1
            if escapes > 8:
                slot._set("未知界面", f"已看到{phrase}，按了 Esc，没有回到主界面")
                return
            try:
                press_escape(hwnd)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return
            slot._set("执行中", f"已看到{phrase}，正在按 Esc 回到主界面")
            continue
        if in_battle(hits, image.width, image.height, image):
            held = None
            slot._set("执行中", f"{task}战斗中")
            continue
        if auto_pathing(hits, image.width, image.height):
            held = None
            slot._set("执行中", f"{task}自动寻路中")
            continue
        if is_state_a(hits, image.width, image.height, image):
            held = None
            slot._set("执行中", f"{task}进行中")
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
            slot._set("执行中", f"{task}进行中，15 秒后再看画面中心")
        else:
            slot._set("执行中", f"{task}进行中，中心画面有变化，先不关")
        held = image
    slot._running = True
    slot._set("执行中", f"已点击「{label}」，{task}进行中，没有看到完成结算")
