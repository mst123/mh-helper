"""认画面。只看截图和识别结果，不点击。"""

import re

from PIL import Image, ImageChops, ImageStat

from app.toolkit.button import ACTIVITY_ICON
from app.toolkit.match import find_pictures, load_picture
from app.windows.ocr import TextHit, read_texts_in

_PROMO_NEEDLES = ("前往报名", "联赛手册")


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def best_hit(hits: list[TextHit], needle: str) -> TextHit | None:
    best: TextHit | None = None
    for hit in hits:
        if needle not in hit.text:
            continue
        if best is None or hit.score > best.score:
            best = hit
    return best


def hit_contains(hits: list[TextHit], needle: str) -> TextHit | None:
    best: TextHit | None = None
    for hit in hits:
        if needle not in compact(hit.text):
            continue
        if best is None or hit.score > best.score:
            best = hit
    return best


def low_text(hits: list[TextHit], image_height: int, needle: str) -> bool:
    floor = image_height * 0.7
    return any(needle in hit.text and hit.y >= floor for hit in hits)


def label_right(hits: list[TextHit], anchor: TextHit, label: str, skip_contains: str = "") -> TextHit | None:
    """锚点右侧同一行的短标签。师门的「参加」「完成」用它，别的每日任务也可以用。"""
    linked: TextHit | None = None
    for button in hits:
        text = compact(button.text)
        if skip_contains and skip_contains in text:
            continue
        if text != label:
            continue
        if not 20 < button.x - anchor.x < 320 or abs(button.y - anchor.y) >= 60:
            continue
        if linked is None or button.x < linked.x:
            linked = button
    return linked


def top_activity(hits: list[TextHit], width: int, height: int) -> bool:
    """上方导航里单独的「活动」两个字。弹窗标题更靠下，日常活动也不算。"""
    for hit in hits:
        if hit.y > height * 0.16:
            continue
        if not 0.18 <= hit.x / max(width, 1) <= 0.65:
            continue
        if compact(hit.text) == "活动":
            return True
    return False


def on_main(hits: list[TextHit], width: int, height: int) -> bool:
    """已经进了游戏：左下角「点击输入」，或上方「活动」。有一个即可。"""
    return low_text(hits, height, "点击输入") or top_activity(hits, width, height)


def character_dialog(hits: list[TextHit]) -> bool:
    return any(compact(hit.text) in ("人物属性", "人物信息") for hit in hits)


# 主界面右下角的包裹图标。对上才算在主界面。
MAIN_BAG = (0.899, 0.805, 0.999, 0.941)
_BAG = None


def _bag():
    global _BAG
    if _BAG is None:
        _BAG = load_picture("包裹-主页面.png")
    return _BAG


def on_state_a(image: Image.Image) -> bool:
    """主界面看右下角包裹图标。对上才算在主界面。"""
    width, height = image.size
    left = int(MAIN_BAG[0] * width)
    top = int(MAIN_BAG[1] * height)
    right = max(left + 1, int(MAIN_BAG[2] * width))
    bottom = max(top + 1, int(MAIN_BAG[3] * height))
    return bool(find_pictures(image.crop((left, top, right, bottom)), _bag(), threshold=0.85, limit=1))


def is_state_a(hits: list[TextHit], width: int, height: int, image=None) -> bool:
    """状态 A。有截图时只看右下角包裹图标。没有截图时才看上方的「活动」。"""
    if image is not None:
        return on_state_a(image)
    if character_dialog(hits):
        return False
    return top_activity(hits, width, height)


def in_battle(hits: list[TextHit], width: int, height: int, image=None) -> bool:
    """战斗页：上方没有「活动」，右下角是「取消」或「自动」。不认头像。"""
    if image is not None and on_state_a(image):
        return False
    if top_activity(hits, width, height):
        return False
    if image is not None and ACTIVITY_ICON.appear(image):
        return False
    for hit in hits:
        if compact(hit.text) not in ("取消", "自动"):
            continue
        if hit.x > width * 0.80 and hit.y > height * 0.85:
            return True
    return False


def promo_open(hits: list[TextHit]) -> bool:
    return any(needle in hit.text for hit in hits for needle in _PROMO_NEEDLES)


def welfare_open(hits: list[TextHit], width: int, height: int) -> bool:
    for hit in hits:
        text = compact(hit.text)
        if "打开刮刮乐" in text or "每日福利" in text or "梦幻刮刮乐" in text:
            return True
        if text == "福利" and abs(hit.x - width * 0.5) < width * 0.2 and hit.y < height * 0.28:
            return True
    return False


def band_changed(before: Image.Image, after: Image.Image, y_ratio: float) -> bool:
    if before.size != after.size:
        return True
    top = max(0, int(round(y_ratio * before.height)) - 40)
    bottom = min(before.height, top + int(before.height * 0.45))
    if bottom <= top:
        return changed(before, after)
    difference = ImageChops.difference(
        before.crop((0, top, before.width, bottom)).convert("RGB"),
        after.crop((0, top, after.width, bottom)).convert("RGB"),
    )
    mean = sum(ImageStat.Stat(difference).mean) / 3
    return mean > 2


def is_black(image: Image.Image) -> bool:
    if image.width <= 0 or image.height <= 0:
        return True
    sample = image.convert("L").resize((32, 32))
    histogram = sample.histogram()
    count = sum(histogram) or 1
    mean = sum(index * value for index, value in enumerate(histogram)) / count
    return mean < 3


def auto_pathing(hits: list[TextHit], width: int, height: int) -> bool:
    """画面中间出现「自动寻路」，说明人物还在走。这时不按 Esc，也不重新点参加。"""
    if any("日常活动" in compact(hit.text) for hit in hits):
        return False
    if character_dialog(hits):
        return False
    for hit in hits:
        if "自动寻路" not in compact(hit.text):
            continue
        if not width * 0.15 < hit.x < width * 0.85:
            continue
        if not height * 0.12 < hit.y < height * 0.78:
            continue
        return True
    return False


def row_button(image: Image.Image, anchor: TextHit, labels: tuple[str, ...]) -> TextHit | None:
    """只认任务名右侧那一行里的按钮文字，避免点到别的行。"""
    width, height = image.size
    if width <= 0 or height <= 0:
        return None
    x0 = max(anchor.x + 36, 0) / width
    x1 = min(anchor.x + 280, width) / width
    y0 = max(anchor.y - 36, 0) / height
    y1 = min(anchor.y + 52, height) / height
    if x1 - x0 < 0.02 or y1 - y0 < 0.01:
        return None
    for hit in read_texts_in(image, x0, y0, x1, y1):
        text = compact(hit.text)
        if "师门" in text or "宝图" in text:
            continue
        for label in labels:
            if text == label:
                return hit
    return None


def center_still(before: Image.Image, after: Image.Image) -> bool:
    """画面中心几乎没变。弹窗停在中间时成立，任务过程中心会变。"""
    if before.size != after.size:
        return False
    left = int(before.width * 0.30)
    right = int(before.width * 0.70)
    top = int(before.height * 0.22)
    bottom = int(before.height * 0.68)
    if right <= left or bottom <= top:
        return False
    difference = ImageChops.difference(
        before.crop((left, top, right, bottom)).convert("RGB"),
        after.crop((left, top, right, bottom)).convert("RGB"),
    )
    mean = sum(ImageStat.Stat(difference).mean) / 3
    return mean < 6


def changed(before: Image.Image, after: Image.Image) -> bool:
    if before.size != after.size:
        return True
    difference = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
    mean = sum(ImageStat.Stat(difference).mean) / 3
    return mean > 2
