"""用小图在截图里找位置，再看同一行右侧近处的按钮颜色。"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# 按钮在图标右边缘之外，按图标宽度计。近处是「活跃」绿字，再过去才是参加或完成。
_NEAR = 3.0
_FAR = 4.7


@dataclass(frozen=True)
class PictureHit:
    score: float
    x: int
    y: int
    width: int
    height: int


def _screen(image: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def find_pictures(image: Image.Image, template: np.ndarray, threshold: float = 0.85, limit: int = 8) -> list[PictureHit]:
    """小图和截图同一缩放。返回每一处左上角，相似度从高到低。"""
    screen = _screen(image)
    height, width = template.shape[:2]
    if screen.shape[0] < height or screen.shape[1] < width:
        return []
    scores = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    found: list[PictureHit] = []
    while len(found) < limit:
        _, best, _, place = cv2.minMaxLoc(scores)
        if float(best) < threshold:
            break
        x, y = place
        found.append(PictureHit(float(best), int(x), int(y), width, height))
        left = max(0, x - width // 2)
        top = max(0, y - height // 2)
        scores[top : min(scores.shape[0], y + height), left : min(scores.shape[1], x + width)] = 0
    return found


def _orange(pixel: np.ndarray) -> bool:
    red, green, blue = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
    return red > 200 and 90 < green < 190 and blue < 120 and red > green + 20


def _button_green(pixel: np.ndarray) -> bool:
    red, green, blue = (int(pixel[0]), int(pixel[1]), int(pixel[2]))
    return green > 140 and green > red + 30 and green > blue + 20


def status_beside(image: Image.Image, hit: PictureHit) -> tuple[str, int, int] | None:
    """图标同一行、右侧不远处的按钮。橙色是参加，绿色是完成。够不着旁边那张卡片。"""
    rgb = np.array(image.convert("RGB"))
    left = int(hit.x + hit.width + _NEAR * hit.width)
    right = int(hit.x + hit.width + _FAR * hit.width)
    top = int(hit.y + hit.height * 0.1)
    bottom = int(hit.y + hit.height * 0.9)
    left = max(0, min(rgb.shape[1] - 1, left))
    right = max(left + 1, min(rgb.shape[1], right))
    top = max(0, min(rgb.shape[0] - 1, top))
    bottom = max(top + 1, min(rgb.shape[0], bottom))
    if right - left < hit.width:
        return None
    crop = rgb[top:bottom, left:right]
    orange_x: list[int] = []
    orange_y: list[int] = []
    green_x: list[int] = []
    green_y: list[int] = []
    for y in range(crop.shape[0]):
        for x in range(crop.shape[1]):
            pixel = crop[y, x]
            if _orange(pixel):
                orange_x.append(left + x)
                orange_y.append(top + y)
            elif _button_green(pixel):
                green_x.append(left + x)
                green_y.append(top + y)
    if len(green_x) >= 40 and len(green_x) > len(orange_x):
        return "完成", int(sum(green_x) / len(green_x)), int(sum(green_y) / len(green_y))
    if len(orange_x) >= 40 and len(orange_x) > len(green_x):
        return "参加", int(sum(orange_x) / len(orange_x)), int(sum(orange_y) / len(orange_y))
    return None


_SHIMEN: np.ndarray | None = None


def shimen_icon() -> np.ndarray:
    global _SHIMEN
    if _SHIMEN is None:
        path = Path(__file__).resolve().parents[1] / "assets" / "shimen.png"
        _SHIMEN = _screen(Image.open(path))
    return _SHIMEN


# 师门、宝图图标只在活动列表这块里找。底下活跃奖励的卷轴不在范围内。
LIST_BOX = (0.224, 0.237, 0.936, 0.684)


def find_pictures_in(
    image: Image.Image,
    template: np.ndarray,
    box: tuple[float, float, float, float] = LIST_BOX,
    threshold: float = 0.85,
    limit: int = 8,
) -> list[PictureHit]:
    """只在比例框里找。返回的坐标仍是整张截图上的像素。"""
    width, height = image.size
    left = max(0, min(width - 1, int(box[0] * width)))
    top = max(0, min(height - 1, int(box[1] * height)))
    right = max(left + 1, min(width, int(box[2] * width)))
    bottom = max(top + 1, min(height, int(box[3] * height)))
    found = find_pictures(image.crop((left, top, right, bottom)), template, threshold, limit)
    return [PictureHit(hit.score, hit.x + left, hit.y + top, hit.width, hit.height) for hit in found]


def load_picture(name: str) -> np.ndarray:
    path = Path(__file__).resolve().parents[1] / "assets" / name
    return _screen(Image.open(path))


def icon_card(image: Image.Image, template: np.ndarray) -> tuple[str, int, int, float, PictureHit] | None:
    """找到图标，并给出同一行右侧按钮。返回值带上图标位置，方便再认卡片上的次数。"""
    found = find_pictures_in(image, template, threshold=0.85, limit=1)
    if not found:
        return None
    status = status_beside(image, found[0])
    if status is None:
        return None
    label, x, y = status
    return label, x, y, found[0].score, found[0]


def region_same(
    before: Image.Image,
    after: Image.Image,
    box: tuple[float, float, float, float],
    threshold: float = 0.97,
) -> bool:
    """同一块跟上一次对得上，就算这段时间画面没变。"""

    def crop(image: Image.Image) -> np.ndarray:
        width, height = image.size
        left = max(0, min(width - 1, int(box[0] * width)))
        top = max(0, min(height - 1, int(box[1] * height)))
        right = max(left + 1, min(width, int(box[2] * width)))
        bottom = max(top + 1, min(height, int(box[3] * height)))
        return np.array(image.crop((left, top, right, bottom)).convert("RGB"))

    left = crop(before)
    right = crop(after)
    if right.shape != left.shape:
        right = cv2.resize(right, (left.shape[1], left.shape[0]))
    score = cv2.matchTemplate(right, left, cv2.TM_CCOEFF_NORMED)
    return float(score[0, 0]) >= threshold


def shimen_card(image: Image.Image) -> tuple[str, int, int, float] | None:
    """找到师门图标，并给出同一行右侧按钮的文字和点击位置。"""
    found = find_pictures_in(image, shimen_icon(), threshold=0.85, limit=1)
    if not found:
        return None
    status = status_beside(image, found[0])
    if status is None:
        return None
    label, x, y = status
    return label, x, y, found[0].score
