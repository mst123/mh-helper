"""认当前角色。点右上角头像，读名字、ID 和门派，再按 Esc 回到状态 A。"""

import re
import time

from app.daily import save_profile
from app.windows.input import click_client_point, click_client_ratio
from app.windows.ocr import TextHit, read_texts
from app.toolkit.dialog import escape_to_state_a
from app.toolkit.screen import compact, is_state_a


def _role_panel(hits: list[TextHit]) -> bool:
    for hit in hits:
        text = compact(hit.text)
        if text in ("人物属性", "人物信息"):
            return True
        if text == "ID" or (text.startswith("ID") and any(char.isdigit() for char in text)):
            return True
    return False


def _panel_tab(hits: list[TextHit], width: int, label: str) -> TextHit | None:
    best: TextHit | None = None
    for hit in hits:
        if compact(hit.text) != label or hit.x < width * 0.82:
            continue
        if best is None or hit.score > best.score:
            best = hit
    return best


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


def read_character(slot, hwnd: int, done=None, on_done=None) -> bool:
    """读到角色就返回真。途中看到任务完成时调用 on_done，并返回假。"""
    slot._character_id = ""
    slot._character_name = ""
    image = slot._grab(hwnd)
    if image is None:
        return False
    hits = read_texts(image)
    seen_done = False
    if not is_state_a(hits, image.width, image.height, image):
        image, seen_done = escape_to_state_a(slot, hwnd, image, done=done)
        if image is None:
            return False
    opened = _role_panel(read_texts(image))
    clicks = 0
    while not opened and clicks < 3:
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
        opened = _role_panel(read_texts(image))
    if not opened:
        slot._set("未知界面", "点了右上角头像，人物属性没有打开")
        return False
    character_id = ""
    name = ""
    for _ in range(4):
        hits = read_texts(image)
        id_hit = _id_hit(hits)
        if id_hit is not None:
            character_id = _id_digits(id_hit)
            name = _name_near(hits, id_hit)
            if character_id:
                break
        tab = _panel_tab(hits, image.width, "属性")
        if tab is None:
            break
        x, y = slot._client_point(hwnd, image, tab.x, tab.y)
        try:
            click_client_point(hwnd, x, y)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return False
        slot._set("执行中", "已点击「属性」")
        time.sleep(0.6)
        image = slot._grab(hwnd)
        if image is None:
            return False
    if not character_id:
        slot._set("未知界面", "人物属性里没有读到角色 ID")
        return False
    school = ""
    for _ in range(4):
        hits = read_texts(image)
        school = _school_name(hits)
        if school:
            break
        tab = _panel_tab(hits, image.width, "信息")
        if tab is None:
            break
        x, y = slot._client_point(hwnd, image, tab.x, tab.y)
        try:
            click_client_point(hwnd, x, y)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return False
        slot._set("执行中", "已点击「信息」")
        time.sleep(0.6)
        image = slot._grab(hwnd)
        if image is None:
            return False
    save_profile(character_id, name, school)
    slot._character_id = character_id
    slot._character_name = name
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
