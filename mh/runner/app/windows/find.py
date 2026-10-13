import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.windll.user32
ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUM_PROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

class WindowMatchError(Exception):
    def __init__(self, status: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class FoundWindow:
    hwnd: int
    title: str


def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def find_window(title_contains: str | list[str]) -> FoundWindow:
    """按标题找一个可见顶层窗口。标题满足任意一条即可。多个时用枚举到的第一个。直接枚举，避免把每个窗口都包成对象后卡住这一路。"""
    if isinstance(title_contains, str):
        needles = [title_contains.strip()]
    else:
        needles = [item.strip() for item in title_contains]
    needles = [item for item in needles if item]
    if not needles:
        raise WindowMatchError("未找到窗口", "窗口标题规则为空")

    matches: list[FoundWindow] = []

    def on_window(hwnd, _lparam) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        title = window_title(int(hwnd))
        if title and any(needle in title for needle in needles):
            matches.append(FoundWindow(hwnd=int(hwnd), title=title))
        return True

    callback = ENUM_PROC(on_window)
    if not user32.EnumWindows(callback, 0):
        raise WindowMatchError("未找到窗口", "无法枚举窗口")

    if not matches:
        joined = "」或「".join(needles)
        raise WindowMatchError("未找到窗口", f"没有标题包含「{joined}」的可见窗口")
    return matches[0]
