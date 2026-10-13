"""开始前确认人已经在主界面。登录、战斗、自动寻路都不往下做。"""

from PIL import Image

from app.windows.ocr import read_texts
from app.toolkit.dialog import escape_to_state_a
from app.toolkit.screen import auto_pathing, compact, in_battle, is_state_a, on_state_a

_LOGIN_WORDS = ("登录游戏", "进入游戏")


def _login_screen(hits) -> bool:
    texts = [compact(hit.text) for hit in hits]
    return any(word in text for text in texts for word in _LOGIN_WORDS)


def ensure_state_a(slot, hwnd: int, image: Image.Image) -> Image.Image | None:
    """已经在状态 A 就直接返回。关得掉的弹窗按 Esc。回不去就停住。"""
    if on_state_a(image):
        return image
    hits = read_texts(image)
    if _login_screen(hits):
        slot._running = False
        slot._set("已停止", "请先进入主界面")
        return None
    if in_battle(hits, image.width, image.height, image):
        slot._running = False
        slot._set("已停止", "当前在战斗中，请先回到主界面")
        return None
    if auto_pathing(hits, image.width, image.height):
        slot._running = False
        slot._set("已停止", "当前在自动寻路，请先回到主界面")
        return None
    if is_state_a(hits, image.width, image.height, image):
        return image
    image, _seen = escape_to_state_a(slot, hwnd, image, hold=in_battle)
    if image is None:
        return None
    if on_state_a(image):
        return image
    hits = read_texts(image)
    if in_battle(hits, image.width, image.height, image):
        slot._running = False
        slot._set("已停止", "当前在战斗中，请先回到主界面")
        return None
    if auto_pathing(hits, image.width, image.height):
        slot._running = False
        slot._set("已停止", "当前在自动寻路，请先回到主界面")
        return None
    if is_state_a(hits, image.width, image.height, image):
        return image
    slot._running = False
    slot._set("已停止", "请先进入主界面")
    return None
