import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_MOUSEWHEEL = 0x020A
INPUT_MOUSE = 0
MOUSEEVENTF_WHEEL = 0x0800
VK_ESCAPE = 0x1B
SCAN_ESCAPE = 0x01
MK_LBUTTON = 0x0001
WHEEL_DELTA = 120

user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL

user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
user32.ChildWindowFromPointEx.restype = wintypes.HWND
user32.MapWindowPoints.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(wintypes.POINT), wintypes.UINT]
user32.MapWindowPoints.restype = ctypes.c_int

_SKIP_CHILD = 0x0001 | 0x0004


def client_size(hwnd: int) -> tuple[int, int]:
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("无法读取客户区尺寸")
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        raise OSError("客户区尺寸无效")
    return width, height


def _receiver(hwnd: int, x: int, y: int) -> tuple[int, int, int]:
    """点会落在最里层的子窗口上。坐标换成那个窗口自己的客户区坐标。"""
    current = int(hwnd)
    point = wintypes.POINT(int(x), int(y))
    for _ in range(8):
        child = user32.ChildWindowFromPointEx(wintypes.HWND(current), point, _SKIP_CHILD)
        child_id = int(child or 0)
        if child_id == 0 or child_id == current:
            break
        mapped = wintypes.POINT(point.x, point.y)
        user32.MapWindowPoints(wintypes.HWND(current), wintypes.HWND(child_id), ctypes.byref(mapped), 1)
        current = child_id
        point = mapped
    return current, int(point.x), int(point.y)


def click_client_point(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """把一次单击送进窗口客户区。不移动鼠标，也不把窗口切到前台。"""
    width, height = client_size(hwnd)
    x = max(0, min(width - 1, int(x)))
    y = max(0, min(height - 1, int(y)))
    target, local_x, local_y = _receiver(hwnd, x, y)
    lparam = (local_y << 16) | (local_x & 0xFFFF)
    handle = wintypes.HWND(target)
    if not user32.PostMessageW(handle, WM_LBUTTONDOWN, MK_LBUTTON, lparam):
        raise OSError("单击按下没有送进窗口")
    time.sleep(0.05)
    if not user32.PostMessageW(handle, WM_LBUTTONUP, 0, lparam):
        raise OSError("单击抬起没有送进窗口")
    return x, y


def scroll_client_point(hwnd: int, x: int, y: int, notches: int) -> None:
    """在客户区某一点发送滚轮。notches 为正向上翻，为负向下翻。不移动鼠标。"""
    width, height = client_size(hwnd)
    x = max(0, min(width - 1, int(x)))
    y = max(0, min(height - 1, int(y)))
    point = wintypes.POINT(x, y)
    if not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(point)):
        raise OSError("无法把滚轮位置换算到屏幕")
    target, _local_x, _local_y = _receiver(hwnd, x, y)
    delta = ctypes.c_short(int(notches) * WHEEL_DELTA).value
    wparam = (delta & 0xFFFF) << 16
    lparam = ((int(point.y) & 0xFFFF) << 16) | (int(point.x) & 0xFFFF)
    if not user32.PostMessageW(wintypes.HWND(target), WM_MOUSEWHEEL, wparam, lparam):
        raise OSError("滚轮没有送进窗口")


def scroll_real(hwnd: int, x: int, y: int, notches: int) -> None:
    """真实滚轮。游戏不吃后台滚轮时用。光标短暂放到列表上，翻完放回去。"""
    width, height = client_size(hwnd)
    x = max(0, min(width - 1, int(x)))
    y = max(0, min(height - 1, int(y)))
    screen = wintypes.POINT(x, y)
    if not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(screen)):
        raise OSError("无法把滚轮位置换算到屏幕")
    previous = _focus_window(hwnd)
    if not _foreground_is(hwnd):
        raise OSError("没能把游戏窗口放到前面，滚轮没有送进去")
    saved = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(saved))
    user32.SetCursorPos(int(screen.x), int(screen.y))
    time.sleep(0.05)
    delta = int(notches) * WHEEL_DELTA
    wheel = INPUT(
        type=INPUT_MOUSE,
        mi=MOUSEINPUT(
            dx=0,
            dy=0,
            mouseData=ctypes.c_ulong(delta & 0xFFFFFFFF).value,
            dwFlags=MOUSEEVENTF_WHEEL,
            time=0,
            dwExtraInfo=0,
        ),
    )
    sent = 0
    try:
        sent = int(user32.SendInput(1, ctypes.byref(wheel), ctypes.sizeof(INPUT)))
        time.sleep(0.08)
    finally:
        user32.SetCursorPos(int(saved.x), int(saved.y))
        if previous and not _foreground_is(previous):
            user32.SetForegroundWindow(wintypes.HWND(previous))
    if sent < 1:
        raise OSError("滚轮没有送进窗口")


kernel32 = ctypes.windll.kernel32
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def _foreground_is(hwnd: int) -> bool:
    current = int(user32.GetForegroundWindow() or 0)
    if current == int(hwnd):
        return True
    root = int(user32.GetAncestor(wintypes.HWND(current), 2) or 0)
    return root == int(hwnd)


def _focus_window(hwnd: int) -> int:
    """把窗口短暂放到前面，返回原来的前台窗口。游戏不吃后台按键。"""
    previous = int(user32.GetForegroundWindow() or 0)
    if _foreground_is(hwnd):
        return previous
    this_thread = int(kernel32.GetCurrentThreadId())
    front_thread = int(user32.GetWindowThreadProcessId(wintypes.HWND(previous), None)) if previous else 0
    attached = False
    if front_thread and front_thread != this_thread:
        attached = bool(user32.AttachThreadInput(this_thread, front_thread, True))
    user32.SetForegroundWindow(wintypes.HWND(hwnd))
    user32.BringWindowToTop(wintypes.HWND(hwnd))
    if attached:
        user32.AttachThreadInput(this_thread, front_thread, False)
    time.sleep(0.08)
    return previous


def press_escape(hwnd: int) -> None:
    """送一次真实的 Esc。游戏不处理后台按键消息，所以先把窗口放到前面。"""
    previous = _focus_window(hwnd)
    if not _foreground_is(hwnd):
        raise OSError("没能把游戏窗口放到前面，Esc 没有送进去")
    down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=VK_ESCAPE, wScan=SCAN_ESCAPE, dwFlags=0))
    up = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(wVk=VK_ESCAPE, wScan=SCAN_ESCAPE, dwFlags=KEYEVENTF_KEYUP),
    )
    sent = user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    time.sleep(0.05)
    sent += user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
    time.sleep(0.12)
    if previous and not _foreground_is(previous):
        user32.SetForegroundWindow(wintypes.HWND(previous))
    if sent < 2:
        raise OSError("Esc 没有送进窗口")


def click_client_ratio(hwnd: int, x_ratio: float, y_ratio: float) -> tuple[int, int]:
    width, height = client_size(hwnd)
    x = int(round((width - 1) * x_ratio))
    y = int(round((height - 1) * y_ratio))
    return click_client_point(hwnd, x, y)
