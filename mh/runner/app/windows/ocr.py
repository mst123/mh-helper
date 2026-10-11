import threading
from dataclasses import dataclass

import numpy as np
from PIL import Image

_ENGINE = None
_LOCK = threading.Lock()


@dataclass(frozen=True)
class TextHit:
    text: str
    score: float
    x: int
    y: int


def _engine():
    global _ENGINE
    with _LOCK:
        if _ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR

            _ENGINE = RapidOCR()
        return _ENGINE


def read_texts(image: Image.Image) -> list[TextHit]:
    """读出截图里的文字和图像像素中心。"""
    return _read(image, 0, 0)


def read_texts_in(image: Image.Image, x0: float, y0: float, x1: float, y1: float) -> list[TextHit]:
    """只认截图里的一块。坐标是相对整张图的比例，返回的中心仍是整张图上的像素。"""
    width, height = image.size
    left = max(0, min(width - 1, int(x0 * width)))
    top = max(0, min(height - 1, int(y0 * height)))
    right = max(left + 1, min(width, int(x1 * width)))
    bottom = max(top + 1, min(height, int(y1 * height)))
    return _read(image.crop((left, top, right, bottom)), left, top)


def _read(image: Image.Image, origin_x: int, origin_y: int) -> list[TextHit]:
    result, _elapsed = _engine()(np.array(image.convert("RGB")))
    hits: list[TextHit] = []
    for box, content, score in result or []:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        hits.append(
            TextHit(
                text=str(content),
                score=float(score),
                x=int(round(sum(xs) / len(xs))) + origin_x,
                y=int(round(sum(ys) / len(ys))) + origin_y,
            )
        )
    return hits


def find_text_center(image: Image.Image, text: str) -> tuple[int, int] | None:
    """在截图里找包含指定文字的区域，返回图像像素中心。找不到则返回空。"""
    needle = text.strip()
    if not needle:
        return None
    best: TextHit | None = None
    for hit in read_texts(image):
        if needle not in hit.text:
            continue
        if best is None or hit.score > best.score:
            best = hit
    if best is None:
        return None
    return best.x, best.y
