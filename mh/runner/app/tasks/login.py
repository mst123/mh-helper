"""进游戏：启动器、登录页、默认区服和角色，然后确认主界面并交给师门。"""

import re
import time

from PIL import Image

from app.windows.capture import CaptureError
from app.windows.find import window_title
from app.windows.input import click_client_point, click_client_ratio, client_size, press_escape, scroll_client_point
from app.windows.ocr import TextHit, find_text_center, read_texts
from app.toolkit.screen import band_changed, best_hit, changed, on_main, promo_open


def _account_in_text(text: str, account: str) -> bool:
    if account in text:
        return True
    parts = re.findall(r"\d+", account)
    if len(parts) < 2:
        return False
    cursor = 0
    for part in parts:
        found = text.find(part, cursor)
        if found < 0:
            return False
        cursor = found + len(part)
    return True


def _account_in_list(hits: list[TextHit], account: str, dropdown_y: int) -> TextHit | None:
    best: TextHit | None = None
    for hit in hits:
        if hit.y <= dropdown_y + 12 or not _account_in_text(hit.text, account):
            continue
        if best is None or hit.y < best.y:
            best = hit
    return best


def press_launcher(slot, hwnd: int, before: Image.Image, button_text: str) -> None:
    image = before
    center = find_text_center(image, button_text)
    deadline = time.time() + 15
    while center is None and time.time() < deadline:
        time.sleep(0.6)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError:
            break
        slot._save(image, "latest.png")
        center = find_text_center(image, button_text)
    if center is None:
        slot._set("未知界面", f"启动器画面上没有找到「{button_text}」")
        return
    width, height = client_size(hwnd)
    image_x, image_y = center
    x = int(round(image_x * width / image.width))
    y = int(round(image_y * height / image.height))
    try:
        x, y = click_client_point(hwnd, x, y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return

    deadline = time.time() + 12
    title = window_title(hwnd)
    while time.time() < deadline and slot.spec.launcher_title in title:
        time.sleep(0.4)
        title = window_title(hwnd) or title
    try:
        after = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", f"已点击「{button_text}」({x}, {y})，随后{exc}")
        return
    slot._save(after, "latest.png")
    slot._save(after, "after.png")
    moved = "画面有变化" if changed(before, after) else "画面没有变化"
    shown = title or "空标题"
    slot._running = True
    slot._set("执行中", f"已点击「{button_text}」({x}, {y})，窗口标题为「{shown}」，{moved}")


def enter_from_login(slot, hwnd: int, before: Image.Image) -> bool:
    account = slot.spec.login_account.strip()
    hits = read_texts(before)
    if best_hit(hits, "进入游戏") is None:
        return False
    try:
        x, y = click_client_ratio(hwnd, slot.spec.login_dropdown.x, slot.spec.login_dropdown.y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return True
    time.sleep(0.6)
    try:
        opened = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", str(exc))
        return True
    slot._save(opened, "latest.png")
    if not band_changed(before, opened, slot.spec.login_dropdown.y):
        slot._set("未知界面", f"已点击账号区域 ({x}, {y})，画面没有变化，账号列表没有打开")
        return True
    slot._set("执行中", "账号列表已打开，正在查找账号")
    dropdown_y = int(round(slot.spec.login_dropdown.y * (opened.height - 1)))

    image = opened
    chosen = _account_in_list(read_texts(opened), account, dropdown_y)
    for step in range(8):
        if chosen is not None:
            break
        time.sleep(0.45)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return True
        slot._save(image, "latest.png")
        chosen = _account_in_list(read_texts(image), account, dropdown_y)
        if chosen is not None:
            break
        direction = -1 if step < 4 else 1
        scroll_x, scroll_y = slot._client_point(
            hwnd,
            image,
            int(round(slot.spec.login_dropdown.x * (image.width - 1))),
            min(image.height - 1, dropdown_y + int(image.height * 0.12)),
        )
        try:
            scroll_client_point(hwnd, scroll_x, scroll_y, direction)
        except OSError as exc:
            slot._set("未知界面", str(exc))
            return True
    if chosen is None:
        slot._set("未知界面", f"账号列表里没有找到「{account}」")
        return True

    x, y = slot._client_point(hwnd, image, chosen.x, chosen.y)
    try:
        click_client_point(hwnd, x, y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return True
    time.sleep(0.4)
    try:
        image = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", f"已选择账号，随后{exc}")
        return True
    enter = best_hit(read_texts(image), "进入游戏")
    if enter is None:
        slot._set("未知界面", "选中账号后没有找到「进入游戏」")
        return True
    x, y = slot._client_point(hwnd, image, enter.x, enter.y)
    try:
        click_client_point(hwnd, x, y)
    except OSError as exc:
        slot._set("未知界面", str(exc))
        return True
    slot._set("执行中", f"已选择「{account}」并点击「进入游戏」，正在进入选服")
    time.sleep(0.8)
    try:
        image = slot._capture_or_fail(hwnd)
    except CaptureError as exc:
        slot._set("截图失败", f"已点击「进入游戏」，随后{exc}")
        return True
    if confirm_server(slot, hwnd, image, 25):
        return True
    slot._save(image, "latest.png")
    slot._set("未知界面", "点击「进入游戏」后没有找到「下一步」或「登录游戏」")
    return True


def confirm_server(slot, hwnd: int, image: Image.Image, appear_timeout: float) -> bool:
    """区服和角色保持画面默认值，只点「下一步」，再点「登录游戏」。"""
    deadline = time.time() + appear_timeout
    clicked_next = False
    while True:
        hits = read_texts(image)
        nxt = None if clicked_next else best_hit(hits, "下一步")
        login = best_hit(hits, "登录游戏")
        if nxt is not None:
            x, y = slot._client_point(hwnd, image, nxt.x, nxt.y)
            try:
                click_client_point(hwnd, x, y)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return True
            slot._set("执行中", "区服和角色保持默认，已点击「下一步」")
            clicked_next = True
            deadline = time.time() + 20
            time.sleep(0.8)
        elif login is not None:
            x, y = slot._client_point(hwnd, image, login.x, login.y)
            try:
                click_client_point(hwnd, x, y)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return True
            slot._set("执行中", "已保持默认区服和角色，并点击「登录游戏」，正在确认主界面")
            time.sleep(1.5)
            try:
                after = slot._capture_or_fail(hwnd)
            except CaptureError as exc:
                slot._set("截图失败", f"已点击「登录游戏」，随后{exc}")
                return True
            slot._save(after, "latest.png")
            if settle_main(slot, hwnd, after, 30):
                return True
            slot._set("未知界面", "已点击「登录游戏」，左下角没有认出主界面")
            return True
        elif time.time() >= deadline:
            if clicked_next:
                slot._set("未知界面", "已点击「下一步」，没有找到「登录游戏」")
                return True
            return False
        else:
            time.sleep(0.6)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return True
        slot._save(image, "latest.png")


def settle_main(slot, hwnd: int, image: Image.Image, appear_timeout: float) -> bool:
    """左下角「点击输入」或上方「活动」有一个，即算进入游戏。活动推送先关掉。"""
    from app.tasks.shimen import run as run_shimen

    deadline = time.time() + appear_timeout
    closed = 0
    while True:
        hits = read_texts(image)
        entered = on_main(hits, image.width, image.height)
        if entered and promo_open(hits):
            closed += 1
            if closed > 3:
                slot._save(image, "latest.png")
                slot._running = True
                slot._set("未知界面", "活动推送没有关掉")
                return True
            try:
                press_escape(hwnd)
            except OSError as exc:
                slot._set("未知界面", str(exc))
                return True
            slot._set("执行中", "已按 Esc 关闭活动推送")
            deadline = max(deadline, time.time() + 8)
            time.sleep(0.7)
        elif entered:
            slot._save(image, "latest.png")
            slot._save(image, "after.png")
            slot._running = True
            if closed:
                slot._set("执行中", "已关闭活动推送，并进入主界面")
            else:
                slot._set("执行中", "已进入主界面")
            run_shimen(slot, hwnd)
            if slot._status == "执行中":
                from app.tasks.baotu import run as run_baotu

                run_baotu(slot, hwnd)
            return True
        elif time.time() >= deadline:
            return False
        else:
            time.sleep(0.6)
        try:
            image = slot._capture_or_fail(hwnd)
        except CaptureError as exc:
            slot._set("截图失败", str(exc))
            return True
        slot._save(image, "latest.png")
