import asyncio
import io
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from PIL import Image
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import load_config
from app.inspect import read_region
from app.session import SessionManager
from app.tasks.catalog import list_tasks
from app.windows.capture import enable_dpi_awareness

enable_dpi_awareness()

_sockets: set[WebSocket] = set()
_manager: SessionManager | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _publish(slots: list[dict]) -> None:
    if _loop is None:
        return
    asyncio.run_coroutine_threadsafe(_broadcast({"type": "slots", "slots": slots}), _loop)


async def _broadcast(payload: dict) -> None:
    dead: list[WebSocket] = []
    for socket in list(_sockets):
        try:
            await socket.send_json(payload)
        except Exception:
            dead.append(socket)
    for socket in dead:
        _sockets.discard(socket)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _manager, _loop
    _loop = asyncio.get_running_loop()
    config = load_config()
    app.state.port = config.port
    _manager = SessionManager(config.slots, _publish)
    yield
    if _manager is not None:
        _manager.stop_all()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_manager() -> SessionManager:
    if _manager is None:
        raise HTTPException(status_code=503, detail="执行器还没准备好")
    return _manager


def _require_slot(slot_id: str):
    slot = _require_manager().get(slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="没有这一路")
    return slot


class TaskBody(BaseModel):
    task: str


class RegionBody(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


@app.get("/api/tasks")
def tasks():
    return list_tasks()


@app.get("/api/slots")
def list_slots():
    return _require_manager().snapshot()


@app.post("/api/slots/{slot_id}/task")
def choose_task(slot_id: str, body: TaskBody):
    slot = _require_slot(slot_id)
    if not slot.select_task(body.task):
        raise HTTPException(status_code=409, detail="任务还在跑，或没有这个任务")
    return slot.public()


@app.post("/api/slots/{slot_id}/clear-character")
def clear_character(slot_id: str):
    slot = _require_slot(slot_id)
    reason = slot.clear_character()
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    return slot.public()


@app.post("/api/slots/{slot_id}/clear-today")
def clear_today_mark(slot_id: str):
    slot = _require_slot(slot_id)
    reason = slot.clear_today_mark()
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    return slot.public()


@app.post("/api/slots/{slot_id}/start")
def start_slot(slot_id: str):
    slot = _require_slot(slot_id)
    slot.start()
    return slot.public()


@app.post("/api/slots/{slot_id}/pause")
def pause_slot(slot_id: str):
    slot = _require_slot(slot_id)
    slot.pause()
    return slot.public()


@app.post("/api/slots/{slot_id}/stop")
def stop_slot(slot_id: str):
    slot = _require_slot(slot_id)
    slot.stop()
    return slot.public()


@app.post("/api/slots/{slot_id}/inspect/capture")
def inspect_capture(slot_id: str):
    slot = _require_slot(slot_id)
    reason = slot.capture_for_inspect()
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    path = slot.debug_path()
    with Image.open(path) as image:
        width, height = image.size
    stamp = int(path.stat().st_mtime * 1000)
    return {
        "width": width,
        "height": height,
        "image_url": f"/api/slots/{slot_id}/inspect.png?t={stamp}",
    }


@app.post("/api/slots/{slot_id}/inspect/upload")
async def inspect_upload(slot_id: str, file: UploadFile = File(...)):
    slot = _require_slot(slot_id)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="没有读到图片")
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片太大")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            rgb = image.convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="这不是一张能打开的图片")
    slot.replace_debug_image(rgb)
    path = slot.debug_path()
    width, height = rgb.size
    stamp = int(path.stat().st_mtime * 1000)
    return {
        "width": width,
        "height": height,
        "image_url": f"/api/slots/{slot_id}/inspect.png?t={stamp}",
    }


@app.get("/api/slots/{slot_id}/inspect.png")
def inspect_image(slot_id: str):
    slot = _require_slot(slot_id)
    path = slot.debug_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="还没有调试截图")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.post("/api/slots/{slot_id}/inspect/read")
def inspect_read(slot_id: str, body: RegionBody):
    slot = _require_slot(slot_id)
    path = slot.debug_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="先截一张图")
    for value in (body.x0, body.y0, body.x1, body.y1):
        if not 0 <= value <= 1:
            raise HTTPException(status_code=400, detail="比例要在 0 到 1 之间")
    with Image.open(path) as image:
        rgb = image.convert("RGB").copy()
    return read_region(rgb, body.x0, body.y0, body.x1, body.y1)


@app.get("/api/slots/{slot_id}/screenshot")
def slot_screenshot(slot_id: str):
    slot = _require_slot(slot_id)
    path = slot.snapshot_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="还没有截图")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


@app.websocket("/ws")
async def slots_socket(socket: WebSocket):
    await socket.accept()
    _sockets.add(socket)
    try:
        if _manager is not None:
            await socket.send_json({"type": "slots", "slots": _manager.snapshot()})
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _sockets.discard(socket)


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    uvicorn.run(app, host="127.0.0.1", port=config.port)
