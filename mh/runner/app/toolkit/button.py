"""位置固定的按钮。先看一小块颜色，点下去要等下一屏的检查点出现。"""

from PIL import Image, ImageStat

from app.windows.ocr import TextHit


class RatioButton:
    """客户区比例上的一小块。颜色接近才算这个按钮在画面上。"""

    def __init__(
        self,
        name: str,
        x: float,
        y: float,
        half_w: float,
        half_h: float,
        color: tuple[int, int, int],
        threshold: int = 42,
    ) -> None:
        self.name = name
        self.x = x
        self.y = y
        self.half_w = half_w
        self.half_h = half_h
        self.color = color
        self.threshold = threshold

    def mean(self, image: Image.Image) -> tuple[int, int, int]:
        width, height = image.size
        left = int((self.x - self.half_w) * width)
        top = int((self.y - self.half_h) * height)
        right = int((self.x + self.half_w) * width)
        bottom = int((self.y + self.half_h) * height)
        crop = image.crop((max(left, 0), max(top, 0), max(right, left + 1), max(bottom, top + 1)))
        return tuple(int(channel) for channel in ImageStat.Stat(crop.convert("RGB")).mean)

    def appear(self, image: Image.Image) -> bool:
        got = self.mean(image)
        return sum(abs(got[index] - self.color[index]) for index in range(3)) <= self.threshold


# 主界面左上角活动图标。列表或人物信息盖住时，这块颜色会变。
ACTIVITY_ICON = RatioButton("活动", 0.311, 0.089, 0.016, 0.017, (188, 130, 80), 42)


def _green(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    return green > 120 and green > red + 15 and green > blue + 20


def _gold(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    return red > 160 and green > 100 and red > blue + 40 and abs(red - green) < 90


def row_mark(image: Image.Image, anchor: TextHit) -> str | None:
    """任务名右侧按钮的颜色。绿色算「完成」，金色算「参加」。认字失败时用。"""
    left = int(anchor.x + 70)
    right = int(anchor.x + 230)
    top = int(anchor.y - 8)
    bottom = int(anchor.y + 42)
    if right <= left or bottom <= top:
        return None
    crop = image.crop((max(left, 0), max(top, 0), right, bottom)).convert("RGB")
    pixels = list(crop.get_flattened_data())
    if len(pixels) < 40:
        return None
    green = sum(1 for pixel in pixels if _green(pixel))
    gold = sum(1 for pixel in pixels if _gold(pixel))
    if green >= 80 and green > gold:
        return "完成"
    if gold >= 80:
        return "参加"
    return None
