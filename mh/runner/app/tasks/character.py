"""认当前角色。点右上角头像，读名字、ID 和门派，再按 Esc 回到状态 A。"""

import re
import time

from app.daily import save_profile
from app.windows.input import click_client_ratio, press_escape
from app.windows.ocr import TextHit, read_texts_in
from app.toolkit.dialog import escape_to_state_a
from app.toolkit.screen import compact, on_state_a

_PROFILE = (0.197, 0.229, 0.339, 0.318)
_SCHOOL = (0.558, 0.236, 0.723, 0.299)
_ATTR_CLICK = (0.9415, 0.350)
_INFO_CLICK = (0.942, 0.494)


def _id_hit(hits: list[TextHit]) -> TextHit | None:
    labels = [hit for hit in hits if compact(hit.text) == "ID" or compact(hit.text).startswith("ID")]
    digits = [hit for hit in hits if re.fullmatch(r"\d{5,}", compact(hit.text))]
    for label in labels:
        if re.search(r"\d{5,}", compact(label.text)) and compact(label.text) != "ID":
            return label
        near = [hit for hit in digits if hit.x > label.x and abs(hit.y - label.y) < 40]
        if near:
            return min(near, key=lambda hit: hit.x)
    return None


def _id_digits(hit: TextHit) -> str:
    found = re.search(r"\d{5,}", compact(hit.text))
    return found.group(0) if found else ""


def _name_near(hits: list[TextHit], id_hit: TextHit) -> str:
    """ID 上方同一列的名字。带等级的那一行优先，避免点到旁边的「双周录」。"""
    candidates: list[TextHit] = []
    for hit in hits:
        if hit.y >= id_hit.y - 8 or hit.y < id_hit.y - 70:
            continue
        if abs(hit.x - id_hit.x) > 180:
            continue
        text = re.sub(r"\d+级$", "", compact(hit.text))
        if not text or text.isdigit() or text in ("人物属性", "人物信息", "ID"):
            continue
        candidates.append(hit)
    graded = [hit for hit in candidates if re.search(r"\d+级$", compact(hit.text))]
    pool = graded or candidates
    if not pool:
        return ""
    best = min(pool, key=lambda hit: (abs(hit.x - id_hit.x), -hit.score))
    return re.sub(r"\d+级$", "", compact(best.text))


def _school_name(hits: list[TextHit]) -> str:
    for hit in hits:
        text = compact(hit.text)
        if "门派贡献" in text or "回门派" in text:
            continue
        if "门派" not in text:
            continue
        rest = text.split("门派", 1)[1]
        if rest and "贡献" not in rest:
            return rest
    label = next((hit for hit in hits if compact(hit.text) == "门派"), None)
    if label is None:
        return ""
    nearest: TextHit | None = None
    for hit in hits:
        text = compact(hit.text)
        if not text or "回门派" in text or "贡献" in text or text == "门派":
            continue
        if not 8 < hit.x - label.x < 260 or abs(hit.y - label.y) > 40:
            continue
        if nearest is None or hit.x < nearest.x:
            nearest = hit
    return compact(nearest.text) if nearest is not None else ""


def _read_profile(image) -> tuple[str, str]:
    hits = read_texts_in(image, *_PROFILE)
    id_hit = _id_hit(hits)
    if id_hit is None:
        return "", ""
    return _id_digits(id_hit), _name_near(hits, id_hit)


def _read_school(image) -> str:
    hits = read_texts_in(image, *_SCHOOL)
    named = _school_name(hits)
    if named:
        return named
    texts = [compact(hit.text) for hit in hits]
    texts = [text for text in texts if text and text != "门派" and "贡献" not in text and "回门派" not in text]
    return texts[0] if texts else ""


def _click_ratio(slot, hwnd: int, point: tuple[float, float], label: str):
    try:
        click_client_ratio(hwnd, point[0], point[1])
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return None
    slot._set("执行中", f"已点击「{label}」")
    time.sleep(0.6)
    return slot._grab(hwnd)


def read_character(slot, hwnd: int, done=None, on_done=None) -> bool:
    """读到角色就返回真。途中看到任务完成时调用 on_done，并返回假。"""
    slot._character_id = ""
    slot._character_name = ""
    image = slot._grab(hwnd)
    if image is None:
        return False
    seen_done = False
    if not on_state_a(image):
        image, seen_done = escape_to_state_a(slot, hwnd, image, done=done)
        if image is None:
            return False
    character_id, name = _read_profile(image)
    clicks = 0
    while not character_id and clicks < 3:
        if slot.stopped():
            return False
        clicks += 1
        point = slot.spec.avatar_button
        try:
            x, y = click_client_ratio(hwnd, point.x, point.y)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return False
        slot._set("执行中", f"已点击右上角头像 ({x}, {y})")
        time.sleep(0.8)
        image = slot._grab(hwnd)
        if image is None:
            return False
        character_id, name = _read_profile(image)
        if character_id:
            break
        image = _click_ratio(slot, hwnd, _ATTR_CLICK, "属性")
        if image is None:
            return False
        character_id, name = _read_profile(image)
    if not character_id:
        slot._set("未知界面", "人物属性里没有读到角色 ID")
        return False
    image = _click_ratio(slot, hwnd, _INFO_CLICK, "信息")
    if image is None:
        return False
    school = _read_school(image)
    save_profile(character_id, name, school)
    slot._character_id = character_id
    slot._character_name = name
    try:
        press_escape(hwnd)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return False
    slot._set("执行中", "已按 Esc 关闭弹窗")
    time.sleep(0.5)
    image = slot._grab(hwnd)
    if image is None:
        return False
    panel_done = False
    if not on_state_a(image):
        image, panel_done = escape_to_state_a(slot, hwnd, image, done=done)
        if image is None:
            return False
    if seen_done or panel_done:
        if on_done is not None:
            on_done()
        slot._running = True
        slot._set("执行中", "已按 Esc 回到主界面，师门完成")
        return False
    school_text = school or "未读到"
    shown = name or character_id
    slot._set("执行中", f"已记录角色 {shown}，ID {character_id}，门派 {school_text}")
    return True
