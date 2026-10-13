"""秘境降妖。前半段和师门一样。没有完成按钮，改看活跃。进本后每 10 秒看是否还在自动战斗。"""

import re
import time

from app.daily import mark_done
from app.windows.input import click_client_point, click_client_ratio, press_escape
from app.windows.ocr import read_texts, read_texts_in
from app.tasks.character import read_character
from app.toolkit.activity import SEARCH, open_daily_list, shot
from app.toolkit.match import PictureHit, find_pictures, icon_card, load_picture, region_same
from app.toolkit.screen import compact, on_state_a
from app.toolkit.scroll import browse_list

TASK = "秘境"
_GUIDE_BOX = (0.010, 0.600, 0.349, 0.971)
_GUIDE_CLICK = (0.708, 0.476, 0.953, 0.537)
_PICK_FIRST = (0.190, 0.800, 0.359, 0.859)
_PICK_SECOND = (0.536, 0.586, 0.652, 0.642)
_ENTER_CLICK = (0.814, 0.781, 0.874, 0.857)
_SKILL_CLICK = (0.768, 0.389, 0.993, 0.488)
_REMAIN_BOX = (0.473, 0.245, 0.660, 0.287)
_NUT_BOX = (0.910, 0.864, 0.999, 0.977)
_STILL = (0.782, 0.193, 0.994, 0.379)
_BOSS_BOX = (0.722, 0.627, 0.946, 0.679)
_CLEAR_BOX = (0.768, 0.417, 0.834, 0.471)
_LEAVE_CLICK = (0.893, 0.493, 0.986, 0.538)
_LOOK_SECONDS = 10
_ICON = None
_GUIDE = None
_PICK = None
_LEVEL = None
_SKILL = None
_NUT = None
_FAIL = None


def _icon():
    global _ICON
    if _ICON is None:
        _ICON = load_picture("秘境降妖.png")
    return _ICON


def _guide():
    global _GUIDE
    if _GUIDE is None:
        _GUIDE = load_picture("云乐游.png")
    return _GUIDE


def _pick():
    global _PICK
    if _PICK is None:
        _PICK = load_picture("秘境选择.png")
    return _PICK


def _level():
    global _LEVEL
    if _LEVEL is None:
        _LEVEL = load_picture("秘境选关.png")
    return _LEVEL


def _skill():
    global _SKILL
    if _SKILL is None:
        _SKILL = load_picture("秘境-新技能.png")
    return _SKILL


def _nut():
    global _NUT
    if _NUT is None:
        _NUT = load_picture("自动战斗螺母.png")
    return _NUT


def _fail():
    global _FAIL
    if _FAIL is None:
        _FAIL = load_picture("秘境-失败.png")
    return _FAIL


def _look(image):
    return icon_card(image, _icon())


def _activity(image, hit: PictureHit) -> tuple[int, int] | None:
    """活跃是 x/25 或 x/50。推荐给双倍，上限就是 50，满了要和 50 比，不和 25 比。"""
    left = max(0, hit.x + int(2.6 * hit.width) - 4)
    right = min(image.width, hit.x + int(4.0 * hit.width) + 4)
    top = max(0, hit.y + int(0.5 * hit.height) - 4)
    bottom = min(image.height, hit.y + int(1.0 * hit.height) + 6)
    if right <= left or bottom <= top:
        return None
    pieces = [compact(item.text) for item in read_texts(image.crop((left, top, right, bottom)))]
    numbers: list[int] = []
    for piece in pieces:
        numbers.extend(int(number) for number in re.findall(r"\d+", piece))
    if len(numbers) < 2:
        return None
    current, limit = numbers[-2], numbers[-1]
    if limit not in (25, 50):
        return None
    return current, limit


def _box_text(image, box: tuple[float, float, float, float]) -> str:
    hits = sorted(read_texts_in(image, *box), key=lambda hit: hit.x)
    return compact("".join(hit.text for hit in hits))


def _remain(image) -> int | None:
    hits = sorted(read_texts_in(image, *_REMAIN_BOX), key=lambda hit: hit.x)
    text = compact("".join(hit.text for hit in hits))
    found = re.search(r"(\d+)\s*次", text)
    if found is None:
        return None
    return int(found.group(1))


def _seen(image, picture, box: tuple[float, float, float, float] | None = None) -> bool:
    if box is None:
        return bool(find_pictures(image, picture, threshold=0.85, limit=1))
    width, height = image.size
    left = int(box[0] * width)
    top = int(box[1] * height)
    right = max(left + 1, int(box[2] * width))
    bottom = max(top + 1, int(box[3] * height))
    return bool(find_pictures(image.crop((left, top, right, bottom)), picture, threshold=0.85, limit=1))


def _wait(slot, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if slot.stopped():
            return False
        time.sleep(min(0.4, deadline - time.time()))
    return not slot.stopped()


def _click_box(slot, hwnd: int, box: tuple[float, float, float, float]) -> bool:
    try:
        click_client_ratio(hwnd, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return False
    return True


def _back_main(slot, hwnd: int, image):
    for _ in range(4):
        if slot.stopped():
            return None
        if on_state_a(image):
            return image
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return None
        time.sleep(0.5)
        image = shot(slot, hwnd)
        if image is None:
            return None
    if on_state_a(image):
        return image
    slot._set("未知界面", "没有回到主界面")
    return None


def _leave(slot, hwnd: int, message: str, done: bool) -> None:
    """点离开。通关才记完成，失败不记。回到主界面再停。"""
    if not _click_box(slot, hwnd, _LEAVE_CLICK):
        return
    if not _wait(slot, 2):
        return
    image = shot(slot, hwnd)
    if image is None:
        return
    if not on_state_a(image):
        slot._set("未知界面", "没有回到主界面")
        return
    if done:
        mark_done(slot._character_id, TASK)
    slot._running = True
    slot._set("执行中", message)


def _settle(slot, hwnd: int, image) -> bool:
    """连续两次不在自动战斗，而且右上那块没变。看失败和通关。"""
    if _seen(image, _fail()):
        try:
            press_escape(hwnd)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return False
        time.sleep(0.5)
        _leave(slot, hwnd, "秘境失败，已回到主界面", done=False)
        return False
    if "通关" in _box_text(image, _CLEAR_BOX):
        _leave(slot, hwnd, "秘境已通关，已回到主界面", done=True)
        return False
    return True


def _enter_ready(image) -> bool:
    """「进入战斗」在就点。认成「进入战战斗」也算。"""
    text = _box_text(image, _BOSS_BOX)
    return "进入" in text and "战斗" in text


def _click_enter(slot, hwnd: int) -> bool:
    if not _click_box(slot, hwnd, _BOSS_BOX):
        return False
    slot._set("执行中", "已点击进入战斗")
    return True


def _watch(slot, hwnd: int) -> None:
    """每 10 秒看自动战斗螺母，并认「进入战斗」。连续两次没有螺母，再比右上那块。"""
    slot._set("执行中", "已进入自动秘境")
    previous = None
    while not slot.stopped():
        if not _wait(slot, _LOOK_SECONDS):
            return
        image = shot(slot, hwnd)
        if image is None:
            return
        if _enter_ready(image):
            if not _click_enter(slot, hwnd):
                return
            previous = None
            continue
        if _seen(image, _nut(), _NUT_BOX):
            previous = None
            slot._set("执行中", "自动战斗中")
            continue
        if previous is None:
            previous = image
            slot._set("执行中", "不在自动战斗")
            continue
        if not region_same(previous, image, _STILL):
            previous = image
            slot._set("执行中", "秘境进行中")
            continue
        if not _settle(slot, hwnd, image):
            return
        previous = None


def _finish(slot, hwnd: int, image) -> None:
    mark_done(slot._character_id, TASK)
    if _back_main(slot, hwnd, image) is None:
        return
    slot._running = True
    slot._set("执行中", "秘境已完成，已回到主界面")


def run(slot, hwnd: int) -> None:
    """打开日常活动，找到秘境。活跃满了就记完成。进本后每 10 秒看是否还在打。"""
    if not slot._character_id and not read_character(slot, hwnd):
        return
    image = open_daily_list(slot, hwnd)
    if image is None:
        return
    image, card = browse_list(slot, hwnd, SEARCH, _look)
    if image is None:
        return
    if card is None:
        slot._set("未知界面", "活动列表里没有找到秘境降妖")
        return
    _label, x, y, _score, hit = card
    activity = _activity(image, hit)
    if activity is None:
        slot._set("未知界面", "没有读到秘境活跃")
        return
    current, limit = activity
    if current >= limit:
        _finish(slot, hwnd, image)
        return
    try:
        click_x, click_y = slot._client_point(hwnd, image, x, y)
        click_client_point(hwnd, click_x, click_y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return
    slot._set("执行中", "已点击「参加」")
    if not _wait(slot, 5):
        return
    image = shot(slot, hwnd)
    if image is None:
        return
    if not _seen(image, _guide(), _GUIDE_BOX):
        slot._set("未知界面", "没有看到云乐游")
        return
    if not _click_box(slot, hwnd, _GUIDE_CLICK):
        return
    slot._set("执行中", "已点击云乐游对话")
    if not _wait(slot, 2):
        return
    image = shot(slot, hwnd)
    if image is None:
        return
    if _seen(image, _pick()):
        if not _click_box(slot, hwnd, _PICK_FIRST):
            return
        slot._set("执行中", "已选择副本")
        if not _wait(slot, 2):
            return
        if not _click_box(slot, hwnd, _PICK_SECOND):
            return
    if not _wait(slot, 2):
        return
    image = shot(slot, hwnd)
    if image is None:
        return
    if _seen(image, _level()):
        remain = _remain(image)
        if remain is None:
            slot._set("未知界面", "没有读到剩余挑战次数")
            return
        if remain == 0:
            _finish(slot, hwnd, image)
            return
        if not _click_box(slot, hwnd, _ENTER_CLICK):
            return
        slot._set("执行中", "已点击进入秘境")
    if not _wait(slot, 2):
        return
    image = shot(slot, hwnd)
    if image is None:
        return
    if not _seen(image, _skill()):
        slot._set("未知界面", "没有看到秘境新技能")
        return
    if not _click_box(slot, hwnd, _SKILL_CLICK):
        return
    _watch(slot, hwnd)
