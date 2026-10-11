from pathlib import Path

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
MAX_SLOTS = 5


class ClickSpec(BaseModel):
    enabled: bool = False
    x: float = 0.5
    y: float = 0.5


class RatioPoint(BaseModel):
    x: float = 0.502
    y: float = 0.477


class SlotSpec(BaseModel):
    id: str
    account_id: str
    title_contains: str | list[str]
    sandbox_name: str = ""
    launcher_title: str = "MyPCLauncher_x64r"
    launcher_button: str = "开始游戏"
    login_account: str = ""
    login_dropdown: RatioPoint = Field(default_factory=RatioPoint)
    popup_close: RatioPoint = Field(default_factory=lambda: RatioPoint(x=0.845, y=0.253))
    welfare_close: RatioPoint = Field(default_factory=lambda: RatioPoint(x=0.948, y=0.170))
    activity_button: RatioPoint = Field(default_factory=lambda: RatioPoint(x=0.311, y=0.089))
    avatar_button: RatioPoint = Field(default_factory=lambda: RatioPoint(x=0.955, y=0.103))
    click: ClickSpec = Field(default_factory=ClickSpec)

    def title_needles(self) -> list[str]:
        raw = self.title_contains
        items = [raw] if isinstance(raw, str) else list(raw)
        return [item.strip() for item in items if isinstance(item, str) and item.strip()]


class AppConfig(BaseModel):
    port: int = 8000
    slots: list[SlotSpec]


def load_config() -> AppConfig:
    path = ROOT / "config.yaml"
    if not path.exists():
        path = ROOT / "config.example.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = AppConfig.model_validate(raw)
    if not config.slots:
        raise ValueError("至少配置 1 路")
    if len(config.slots) > MAX_SLOTS:
        raise ValueError(f"最多 {MAX_SLOTS} 路")
    ids = [slot.id for slot in config.slots]
    if len(ids) != len(set(ids)):
        raise ValueError("路编号不能重复")
    for slot in config.slots:
        if not slot.title_needles():
            raise ValueError(f"{slot.id} 的窗口标题规则为空")
        points = (
            ("点击坐标", slot.click.x, slot.click.y),
            ("账号下拉坐标", slot.login_dropdown.x, slot.login_dropdown.y),
            ("活动推送关闭坐标", slot.popup_close.x, slot.popup_close.y),
            ("福利页关闭坐标", slot.welfare_close.x, slot.welfare_close.y),
            ("活动按钮坐标", slot.activity_button.x, slot.activity_button.y),
            ("头像坐标", slot.avatar_button.x, slot.avatar_button.y),
        )
        for name, px, py in points:
            if not 0 <= px <= 1 or not 0 <= py <= 1:
                raise ValueError(f"{slot.id} 的{name}必须在 0 到 1 之间")
    return config
