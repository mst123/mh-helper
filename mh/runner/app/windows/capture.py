import asyncio
import ctypes
import threading
from ctypes import wintypes

import numpy as np
from PIL import Image
from winsdk.windows.ai.machinelearning import LearningModelDevice, LearningModelDeviceKind
from winsdk.windows.graphics.capture import Direct3D11CaptureFramePool
from winsdk.windows.graphics.capture.interop import create_for_window
from winsdk.windows.graphics.directx import DirectXPixelFormat
from winsdk.windows.graphics.imaging import BitmapBufferAccessMode, SoftwareBitmap

user32 = ctypes.windll.user32
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL

_DEVICE = threading.local()


class CaptureError(Exception):
    pass


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            return


def _device():
    device = getattr(_DEVICE, "value", None)
    if device is not None:
        return device
    try:
        device = LearningModelDevice(LearningModelDeviceKind.DIRECT_X_HIGH_PERFORMANCE).direct3_d11_device
    except Exception as exc:
        raise CaptureError("无法创建截图设备") from exc
    if device is None:
        raise CaptureError("无法创建截图设备")
    _DEVICE.value = device
    return device


def _frame_bounds(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    handle = wintypes.HWND(hwnd)
    # 按窗口截到的画面通常对齐扩展边框，而不是 GetWindowRect 的外沿。
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(handle, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    if hr != 0 and not user32.GetWindowRect(handle, ctypes.byref(rect)):
        raise CaptureError("无法读取窗口范围")
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _crop_client(hwnd: int, image: Image.Image) -> Image.Image:
    client = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    handle = wintypes.HWND(hwnd)
    if not user32.GetClientRect(handle, ctypes.byref(client)):
        raise CaptureError("无法读取客户区范围")
    if not user32.ClientToScreen(handle, ctypes.byref(origin)):
        raise CaptureError("无法定位客户区")

    client_width = int(client.right - client.left)
    client_height = int(client.bottom - client.top)
    if client_width <= 0 or client_height <= 0:
        raise CaptureError("客户区尺寸无效")
    if abs(image.width - client_width) <= 2 and abs(image.height - client_height) <= 2:
        return image

    left, top, right, bottom = _frame_bounds(hwnd)
    bounds_width = right - left
    bounds_height = bottom - top
    if bounds_width <= 0 or bounds_height <= 0:
        raise CaptureError("窗口范围无效")
    scale_x = image.width / bounds_width
    scale_y = image.height / bounds_height
    if abs(scale_x - scale_y) > 0.08 or not 0.5 <= scale_x <= 4:
        raise CaptureError(
            f"截图尺寸和窗口对不上：图 {image.width}x{image.height}，外框 {bounds_width}x{bounds_height}"
        )

    crop_left = int(round((origin.x - left) * scale_x))
    crop_top = int(round((origin.y - top) * scale_y))
    crop_right = int(round(crop_left + client_width * scale_x))
    crop_bottom = int(round(crop_top + client_height * scale_y))
    crop_left = max(0, min(crop_left, image.width - 1))
    crop_top = max(0, min(crop_top, image.height - 1))
    crop_right = max(crop_left + 1, min(crop_right, image.width))
    crop_bottom = max(crop_top + 1, min(crop_bottom, image.height))
    return image.crop((crop_left, crop_top, crop_right, crop_bottom))


def _bitmap_to_image(bitmap: SoftwareBitmap) -> Image.Image:
    access = getattr(BitmapBufferAccessMode, "READ", BitmapBufferAccessMode.READ_WRITE)
    buffer = bitmap.lock_buffer(access)
    try:
        plane = buffer.get_plane_description(0)
        raw = np.frombuffer(buffer.create_reference(), dtype=np.uint8)
        start = int(plane.start_index)
        stride = int(plane.stride)
        width = int(plane.width)
        height = int(plane.height)
        rows = raw[start : start + stride * height].reshape((height, stride))
        bgra = np.array(rows[:, : width * 4].reshape((height, width, 4)))
    finally:
        closer = getattr(buffer, "close", None)
        if closer is not None:
            closer()
    rgb = bgra[:, :, [2, 1, 0]]
    return Image.fromarray(rgb, mode="RGB")


async def _copy_surface(surface) -> SoftwareBitmap:
    bitmap = await SoftwareBitmap.create_copy_from_surface_async(surface)
    if bitmap is None:
        raise CaptureError("没有拿到画面数据")
    return bitmap


def capture_client_image(hwnd: int) -> Image.Image:
    handle = wintypes.HWND(hwnd)
    if not user32.IsWindow(handle):
        raise CaptureError("窗口已经不在")
    if user32.IsIconic(handle):
        raise CaptureError("窗口已最小化，先把游戏窗口从任务栏打开")

    item = create_for_window(hwnd)
    size = item.size
    if int(size.width) <= 0 or int(size.height) <= 0:
        raise CaptureError("窗口尺寸无效")

    pool = Direct3D11CaptureFramePool.create_free_threaded(
        _device(),
        DirectXPixelFormat.B8_G8_R8_A8_UINT_NORMALIZED,
        2,
        size,
    )
    session = pool.create_capture_session(item)
    for name, value in (("is_cursor_capture_enabled", False), ("is_border_required", False)):
        if hasattr(session, name):
            try:
                setattr(session, name, value)
            except Exception:
                pass

    arrived = threading.Event()
    holder: dict = {}

    def on_frame(frame_pool, _args) -> None:
        if holder.get("frame") is not None:
            return
        frame = frame_pool.try_get_next_frame()
        if frame is None:
            return
        holder["frame"] = frame
        arrived.set()

    token = pool.add_frame_arrived(on_frame)
    try:
        session.start_capture()
        if not arrived.wait(3):
            raise CaptureError("截图超时")
        frame = holder.get("frame")
        if frame is None:
            raise CaptureError("没有截到画面")
        bitmap = asyncio.run(_copy_surface(frame.surface))
        image = _bitmap_to_image(bitmap)
    finally:
        remover = getattr(pool, "remove_frame_arrived", None)
        if remover is not None:
            try:
                remover(token)
            except Exception:
                pass
        for target in (session, pool, holder.get("frame")):
            closer = getattr(target, "close", None)
            if closer is not None:
                try:
                    closer()
                except Exception:
                    pass

    return _crop_client(hwnd, image)
