"""对已经截下的调试图认一块区域。不再截新图，也不点击。"""

from PIL import Image, ImageStat

from app.toolkit.button import _gold, _green
from app.windows.ocr import read_texts_in


def _box(width: int, height: int, x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
    left = max(0, min(width - 1, int(min(x0, x1) * width)))
    top = max(0, min(height - 1, int(min(y0, y1) * height)))
    right = max(left + 1, min(width, int(max(x0, x1) * width)))
    bottom = max(top + 1, min(height, int(max(y0, y1) * height)))
    return left, top, right, bottom


def read_region(image: Image.Image, x0: float, y0: float, x1: float, y1: float) -> dict:
    """比例框内的文字、平均色，以及绿色、金色像素个数。"""
    width, height = image.size
    left, top, right, bottom = _box(width, height, x0, y0, x1, y1)
    crop = image.crop((left, top, right, bottom)).convert("RGB")
    mean = tuple(int(channel) for channel in ImageStat.Stat(crop).mean)
    pixels = list(crop.getdata())
    green = sum(1 for pixel in pixels if _green(pixel))
    gold = sum(1 for pixel in pixels if _gold(pixel))
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1))))
    y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    texts = []
    for hit in read_texts_in(image, x0, y0, x1, y1):
        texts.append(
            {
                "text": hit.text,
                "score": round(hit.score, 3),
                "x": round(hit.x / max(width, 1), 4),
                "y": round(hit.y / max(height, 1), 4),
            }
        )
    return {
        "x0": round(x0, 4),
        "y0": round(y0, 4),
        "x1": round(x1, 4),
        "y1": round(y1, 4),
        "width": width,
        "height": height,
        "color": {"r": mean[0], "g": mean[1], "b": mean[2]},
        "green": green,
        "gold": gold,
        "pixels": len(pixels),
        "texts": texts,
    }
