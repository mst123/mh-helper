import os
import threading
import time
from collections import deque
from pathlib import Path
from queue import Empty, Queue

from PIL import Image

from app.config import ROOT, SlotSpec
from app.daily import clear_today
from app.evidence import ClickGuard, append_status, dump_error
from app.tasks.catalog import run_task, task_name
from app.tasks.character import read_character
from app.tasks.prepare import ensure_state_a
from app.toolkit.screen import is_black
from app.windows.capture import CaptureError, capture_client_image
from app.windows.find import WindowMatchError, find_window
from app.windows.input import client_size

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
        self._task_id = "shimen"
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

    def debug_path(self) -> Path:
        return DATA_DIR / self.spec.id / "debug.png"

    def capture_for_inspect(self) -> str | None:
        """为识别调试截一张。任务还在跑时不截，避免和任务抢同一窗口。"""
        if self.busy():
            return "任务还在跑，先停止再截图"
        try:
            found = find_window(self.spec.title_needles())
        except WindowMatchError as exc:
            return exc.detail
        try:
            image = self._capture_or_fail(found.hwnd)
        except CaptureError as exc:
            return str(exc)
        self._hwnd = found.hwnd
        self._save(image, "debug.png")
        return None

    def replace_debug_image(self, image: Image.Image) -> None:
        """用一张本地图替换识别调试的底图。不截窗口，也不改任务截图。"""
        self._save(image.convert("RGB"), "debug.png")

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
                "task_id": self._task_id,
                "character_id": self._character_id,
                "character_name": self._character_name,
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
            self._set("暂停", "任务已暂停")
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
        if launcher_title and launcher_title in found.title:
            self._running = False
            self._set("已停止", "请先进入主界面")
            return
        ready = ensure_state_a(self, found.hwnd, before)
        if ready is None:
            self._running = False
            return
        if not self._character_id:
            if not read_character(self, found.hwnd):
                self._running = False
                return
        name = task_name(self._task_id)
        if not name:
            self._running = False
            self._set("已停止", "没有这个任务")
            return
        self._running = True
        self._set("执行中", f"开始「{name}」")
        run_task(self, found.hwnd, self._task_id)
        self._close_task()

    def busy(self) -> bool:
        with self._lock:
            return self._status in ("执行中", "暂停")

    def select_task(self, task_id: str) -> bool:
        if self.busy() or not task_name(task_id):
            return False
        with self._lock:
            self._task_id = task_id
        self._on_change()
        return True

    def clear_character(self) -> str | None:
        if self.busy():
            return "任务还没停止"
        self._character_id = ""
        self._character_name = ""
        self._set(self._idle_status(), "已清除当前角色，下次开始会重新读取")
        return None

    def clear_today_mark(self) -> str | None:
        if self.busy():
            return "任务还没停止"
        if not self._character_id:
            return "还没有角色记录"
        clear_today(self._character_id)
        shown = self._character_name or self._character_id
        self._set(self._idle_status(), f"已清除「{shown}」今日的完成标记")
        return None

    def _idle_status(self) -> str:
        with self._lock:
            if self._status == "排队":
                return "排队"
        return "已停止"

    def _close_task(self) -> None:
        if self._status == "暂停":
            return
        if self._status in ("未知界面", "截图失败", "需要人工"):
            self._running = False
            return
        if self._abort:
            self._running = False
            return
        self._running = False
        self._set("已停止", self._detail)

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
