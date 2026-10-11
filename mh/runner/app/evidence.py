"""出错时留下最近几张图，同一个按钮点太多次就停手。"""

import re
import time
from collections import Counter, deque
from pathlib import Path

from PIL import Image

_CLICK = re.compile(r"已点击「([^」]+)」")


class ClickGuard:
    """最近几次点击如果总是同一个按钮，说明卡住了。"""

    def __init__(self) -> None:
        self._names: deque[str] = deque(maxlen=12)

    def clear(self) -> None:
        self._names.clear()

    def note(self, detail: str) -> str | None:
        found = _CLICK.search(detail)
        if found is None:
            return None
        self._names.append(found.group(1))
        count = Counter(self._names).most_common(2)
        if not count:
            return None
        if count[0][1] >= 8:
            name = count[0][0]
            self.clear()
            return name
        if len(count) >= 2 and count[0][1] >= 6 and count[1][1] >= 6:
            name = f"{count[0][0]}、{count[1][0]}"
            self.clear()
            return name
        return None


def append_status(path: Path, status: str, detail: str) -> None:
    """状态变化写一行。文件太大时只留结尾。不写账号和密码。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%H:%M:%S')} {status} {detail}\n"
    if path.exists() and path.stat().st_size > 200_000:
        text = path.read_text(encoding="utf-8", errors="replace")
        kept = "\n".join(text.splitlines()[-80:])
        path.write_text(kept + "\n" + line, encoding="utf-8")
        return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def dump_error(folder: Path, images: list[Image.Image], status: str, detail: str) -> Path:
    """把最近几张图和原因写到 error 目录，方便事后看停在哪一屏。"""
    target = folder / "error" / time.strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    for index, image in enumerate(images, start=1):
        image.save(target / f"{index:02d}.png", format="PNG")
    (target / "reason.txt").write_text(f"{status}\n{detail}\n", encoding="utf-8")
    return target
