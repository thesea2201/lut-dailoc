from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str
    threshold: float = 4000.0

    @classmethod
    def from_env(cls) -> Optional["TelegramConfig"]:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        threshold_raw = os.getenv("TELEGRAM_THRESHOLD")
        if not token or not chat_id:
            return None
        threshold = float(threshold_raw) if threshold_raw else 4000.0
        return cls(bot_token=token, chat_id=chat_id, threshold=threshold)


def send_message(text: str, config: TelegramConfig) -> None:
    url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"
    payload = {
        "chat_id": config.chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram API responded with status {response.status}")


Reading = Tuple[str, float, Optional[str]]


def maybe_notify(readings: Sequence[Reading], config: Optional[TelegramConfig] = None) -> None:
    cfg = config or TelegramConfig.from_env()
    if cfg is None:
        return

    exceeded: list[Reading] = [reading for reading in readings if reading[1] > cfg.threshold]
    if not exceeded:
        return

    lines = [
        "⚠️ <b>Cảnh báo lưu lượng</b>",
        f"Ngưỡng: {cfg.threshold:g} m3/s",
        "",
    ]
    for label, value, timestamp in exceeded:
        if timestamp:
            lines.append(f"• {label}: {value:g} m3/s lúc {timestamp}")
        else:
            lines.append(f"• {label}: {value:g} m3/s")

    send_message("\n".join(lines), cfg)
