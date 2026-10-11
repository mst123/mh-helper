import os
import threading
import time
from collections import deque
from pathlib import Path
from queue import Empty, Queue

from PIL import Image

from app.config import ROOT, SlotSpec
from app.evidence import ClickGuard, append_status, dump_error
from app.tasks.login import confirm_server, enter_from_login, press_launcher, settle_main
from app.toolkit.screen import changed, is_black
from app.windows.capture import CaptureError, capture_client_image
from app.windows.find import WindowMatchError, find_window
from app.windows.input import click_client_ratio, client_size

DATA_DIR = ROOT / "data" / "slots"


class SlotRuntime:
    def __init__(self, spec: SlotSpec, on_change) -> None:
        self.spec = spec
        self._on_change = on_change
        self._lock = threading.Lock()
        self._commands: Queue[str] = Queue()
        self._status = "排队"
        self._detail = ""
        self._hwnd: int | None = None
        self._running = False
        self._character_id = ""
        self._character_name = ""
        self._screenshot_mtime = 0.0
        self._recent: deque[Image.Image] = deque(maxlen=6)
        self._clicks = ClickGuard()
        self._logged = ("", "")
        self._abort = False
        self._in_guard = False
        self._thread = threading.Thread(target=self._loop, name=f"slot-{spec.id}", daemon=True)
        self._thread.start()

    def start(self) -> None:
        self._commands.put("start")

    def pause(self) -> None:
        self._commands.put("pause")

    def stop(self) -> None:
        self._commands.put("stop")

    def snapshot_path(self) -> Path:
        return DATA_DIR / self.spec.id / "latest.png"

    def public(self) -> dict:
        with self._lock:
            screenshot_url = None
            if self._screenshot_mtime:
                stamp = int(self._screenshot_mtime * 1000)
                screenshot_url = f"/api/slots/{self.spec.id}/screenshot?t={stamp}"
            run_mode = self.spec.sandbox_name.strip() or "直接启动"
            return {
                "id": self.spec.id,
                "account_id": self.spec.account_id,
                "run_mode": run_mode,
                "sandbox_name": self.spec.sandbox_name,
                "status": self._status,
                "detail": self._detail,
                "screenshot_url": screenshot_url,
                "updated_at": self._screenshot_mtime or time.time(),
            }

    def _set(self, status: str, detail: str) -> None:
        with self._lock:
            changed_text = (self._status, self._detail) != (status, detail)
            self._status = status
            self._detail = detail
        self._on_change()
        if changed_text:
            self._write_status(status, detail)
            if status in ("未知界面", "截图失败", "需要人工"):
                self._keep_error(status, detail)
        if self._in_guard:
            return
        stuck = self._clicks.note(detail)
        if stuck is None:
            return
        self._in_guard = True
        self._abort = True
        self._running = False
        self._set("需要人工", f"「{stuck}」点得太多，先停下来。最近几张图在 error 目录")
        self._in_guard = False

    def _loop(self) -> None:
        last_shot = 0.0
        while True:
            try:
                command = self._commands.get(timeout=0.2)
            except Empty:
                command = None
            if command == "start":
                self._begin()
                last_shot = time.time()
            elif command == "pause":
                self._pause()
            elif command == "stop":
                self._halt()
            elif self._running and time.time() - last_shot >= 1:
                self._refresh()
                last_shot = time.time()

    def _take(self, command: str) -> bool:
        found = False
        leftover: list[str] = []
        while True:
            try:
                item = self._commands.get_nowait()
            except Empty:
                break
            if item == command:
                found = True
            else:
                leftover.append(item)
        for item in leftover:
            self._commands.put(item)
        return found

    def stopped(self) -> bool:
        if self._take("stop"):
            self._halt()
            return True
        if self._take("pause"):
            self._running = True
            self._set("暂停", "师门操作已暂停")
            return True
        return self._abort

    def _begin(self) -> None:
        self._running = False
        self._abort = False
        self._clicks.clear()
        self._recent.clear()
        self._set("执行中", "正在查找窗口")
        try:
            found = find_window(self.spec.title_needles())
        except WindowMatchError as exc:
            self._hwnd = None
            self._set(exc.status, exc.detail)
            return

        self._hwnd = found.hwnd
        try:
            before = self._capture_or_fail(found.hwnd)
        except CaptureError as exc:
            self._set("截图失败", str(exc))
            return

        self._save(before, "latest.png")
        self._save(before, "before.png")
        if self._take("stop"):
            self._running = False
            self._set("已停止", "已停止")
            return
        if self._take("pause"):
            self._running = True
            self._set("暂停", f"已连接「{found.title}」，点击已暂停")
            return
        launcher_title = self.spec.launcher_title.strip()
        launcher_button = self.spec.launcher_button.strip()
        if launcher_title and launcher_button and launcher_title in found.title:
            press_launcher(self, found.hwnd, before, launcher_button)
            return
        if self.spec.login_account.strip() and enter_from_login(self, found.hwnd, before):
            return
        if confirm_server(self, found.hwnd, before, 0):
            return
        if settle_main(self, found.hwnd, before, 0):
            return
        if not self.spec.click.enabled:
            self._running = True
            self._set("执行中", f"已连接「{found.title}」，点击未启用")
            return

        try:
            x, y = click_client_ratio(found.hwnd, self.spec.click.x, self.spec.click.y)
            after = self._capture_or_fail(found.hwnd)
        except (OSError, CaptureError) as exc:
            self._set("截图失败", str(exc))
            return

        self._save(after, "latest.png")
        self._save(after, "after.png")
        moved = "画面有变化" if changed(before, after) else "画面没有变化"
        self._running = True
        self._set("执行中", f"已点击客户区 ({x}, {y})，{moved}")

    def _client_point(self, hwnd: int, image: Image.Image, image_x: int, image_y: int) -> tuple[int, int]:
        width, height = client_size(hwnd)
        x = int(round(image_x * width / image.width))
        y = int(round(image_y * height / image.height))
        return x, y

    def _grab(self, hwnd: int) -> Image.Image | None:
        try:
            image = self._capture_or_fail(hwnd)
        except CaptureError as exc:
            self._set("截图失败", str(exc))
            return None
        self._save(image, "latest.png")
        return image

    def _pause(self) -> None:
        if not self._running:
            return
        with self._lock:
            status = self._status
        if status == "暂停":
            return
        self._set("暂停", "已暂停，不再点击")

    def _halt(self) -> None:
        self._running = False
        self._hwnd = None
        self._set("已停止", "已停止")

    def _refresh(self) -> None:
        hwnd = self._hwnd
        if hwnd is None:
            return
        try:
            image = self._capture_or_fail(hwnd)
        except CaptureError as exc:
            self._running = False
            self._set("截图失败", str(exc))
            return
        self._save(image, "latest.png")
        self._on_change()

    def _capture_or_fail(self, hwnd: int) -> Image.Image:
        image = capture_client_image(hwnd)
        if is_black(image):
            raise CaptureError("截到的客户区是黑图")
        return image

    def _save(self, image: Image.Image, name: str) -> None:
        folder = DATA_DIR / self.spec.id
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        temporary = folder / f".{name}.tmp"
        image.save(temporary, format="PNG")
        os.replace(temporary, target)
        if name == "latest.png":
            self._recent.append(image.copy())
            with self._lock:
                self._screenshot_mtime = time.time()

    def _write_status(self, status: str, detail: str) -> None:
        if (status, detail) == self._logged:
            return
        self._logged = (status, detail)
        try:
            append_status(DATA_DIR / self.spec.id / "status.log", status, detail)
        except OSError:
            return

    def _keep_error(self, status: str, detail: str) -> None:
        try:
            dump_error(DATA_DIR / self.spec.id, list(self._recent), status, detail)
        except OSError:
            return


class SessionManager:
    def __init__(self, specs: list[SlotSpec], publish) -> None:
        self._publish = publish
        self._slots = [SlotRuntime(spec, self._notify) for spec in specs]
        self._by_id = {slot.spec.id: slot for slot in self._slots}

    def _notify(self) -> None:
        self._publish(self.snapshot())

    def snapshot(self) -> list[dict]:
        return [slot.public() for slot in self._slots]

    def get(self, slot_id: str) -> SlotRuntime | None:
        return self._by_id.get(slot_id)

    def stop_all(self) -> None:
        for slot in self._slots:
            slot.stop()
