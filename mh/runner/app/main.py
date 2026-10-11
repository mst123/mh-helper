import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import load_config
from app.session import SessionManager
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


@app.get("/api/slots")
def list_slots():
    return _require_manager().snapshot()


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
