#!/usr/bin/env python3
"""Fetch Tram Ái Nghĩa water levels from Google Sheets and plot a line chart."""

from __future__ import annotations

import argparse
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple
from urllib.request import urlopen

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from telegram_notifier import TelegramConfig, send_message

SHEET_ID = "1f659giCGHHzrndi2zmJYy82DTNzeOfmro_CxNz-QrMA"
SHEET_GID = "2051862179"
DEFAULT_SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"
)

THRESHOLDS: Tuple[Tuple[str, float], ...] = (
    ("BĐ1", 6.5),
    ("BĐ2", 8.0),
    ("BĐ3", 9.0),
)

STYLE_PRESETS = {
    "desktop": {
        "figsize": (12, 6),
        "title_size": 18,
        "label_size": 12,
        "tick_size": 11,
        "legend_size": 11,
        "annot_size": 11,
    },
    "mobile": {
        "figsize": (6.5, 10),
        "title_size": 20,
        "label_size": 14,
        "tick_size": 13,
        "legend_size": 13,
        "annot_size": 13,
    },
}


def get_style(style_name: str) -> dict:
    return STYLE_PRESETS.get(style_name, STYLE_PRESETS["desktop"])


def download_sheet_csv(sheet_url: str) -> str:
    """Download the Google Sheet as CSV text."""

    with urlopen(sheet_url, timeout=15) as response:  # nosec B310 - user-provided endpoint
        status = getattr(response, "status", response.getcode())
        if status != 200:
            raise RuntimeError(f"Failed to download sheet (status {status})")
        csv_bytes = response.read()
    return csv_bytes.decode("utf-8-sig")


def parse_csv_content(csv_text: str) -> list[dict[str, str]]:
    """Convert CSV text into a list of dict rows."""

    reader = csv.DictReader(io.StringIO(csv_text))
    return [row for row in reader if any(row.values())]


def parse_csv_file(csv_path: Path) -> list[dict[str, str]]:
    """Load rows from a local CSV file."""

    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if any(row.values())]


def build_series(records: Iterable[dict[str, str]], ma_tram: str) -> Tuple[list[datetime], list[float]]:
    """Filter rows for the requested station and parse time/value columns."""

    cleaned: list[tuple[datetime, float]] = []
    for row in records:
        if row.get("ma_tram") != ma_tram:
            continue
        timestamp = row.get("thoi_gian", "").strip()
        value = row.get("so_lieu", "").strip()
        if not timestamp or not value:
            continue
        try:
            parsed_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            parsed_value = float(value)
        except ValueError:
            continue
        cleaned.append((parsed_time, parsed_value))

    if not cleaned:
        raise ValueError(f"No valid data points found for station {ma_tram}")

    cleaned.sort(key=lambda item: item[0])
    times, values = zip(*cleaned)
    return list(times), list(values)


def notify_if_threshold_exceeded(
    timeline: list[datetime],
    values: list[float],
    ma_tram: str,
    config: TelegramConfig | None,
) -> None:
    """Send Telegram alert if latest value is above BĐ3 and still rising."""

    if config is None or len(values) < 2:
        return

    label, level = THRESHOLDS[-1]
    last_value, prev_value = values[-1], values[-2]
    if last_value <= level or last_value <= prev_value:
        return

    last_time = timeline[-1].strftime("%Y-%m-%d %H:%M")
    prev_time = timeline[-2].strftime("%Y-%m-%d %H:%M")
    message = (
        "\n".join(
            [
                f"⚠️ Mực nước trạm {ma_tram} đạt {last_value:.2f} m lúc {last_time}",
                f"• Vượt {label} ({level:.2f} m)",
                f"• Tiếp tục tăng từ {prev_value:.2f} m lúc {prev_time}",
            ]
        )
    )

    try:
        send_message(message, config)
        print("Đã gửi cảnh báo Telegram.")
    except Exception as exc:
        print(f"Không thể gửi cảnh báo Telegram: {exc}")


def resolve_telegram_config(token: str | None, chat_id: str | None) -> TelegramConfig | None:
    """Build TelegramConfig from CLI args or environment."""

    threshold = THRESHOLDS[-1][1]
    if token or chat_id:
        if not token or not chat_id:
            raise ValueError("Cần cung cấp cả token và chat ID khi dùng tham số CLI.")
        return TelegramConfig(bot_token=token, chat_id=chat_id, threshold=threshold)

    config = TelegramConfig.from_env()
    if config:
        config.threshold = threshold
    return config


def plot_series(
    timeline: list[datetime],
    values: list[float],
    output_path: Path,
    show: bool,
    ma_tram: str,
    style_name: str = "desktop",
) -> None:
    """Render a line chart and save (or optionally show) the figure."""

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    style = get_style(style_name)
    fig, ax = plt.subplots(figsize=style["figsize"])
    ax.plot(timeline, values, color="tab:blue", linewidth=2, label="Mực nước")

    last_time, last_value = timeline[-1], values[-1]
    ax.scatter([last_time], [last_value], color="tab:blue", zorder=5, edgecolor="white")
    ax.annotate(
        f"{last_value:.2f} m",
        xy=(last_time, last_value),
        xytext=(0, -28),
        textcoords="offset points",
        ha="center",
        va="top",
        fontsize=style["annot_size"],
        fontweight="bold",
        color="tab:blue",
        bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "tab:blue", "lw": 1.0},
    )

    colors = {"BĐ1": "tab:orange", "BĐ2": "tab:red", "BĐ3": "tab:purple"}
    for label, level in THRESHOLDS:
        ax.axhline(level, color=colors.get(label, "gray"), linestyle="--", linewidth=1.3, label=f"{label} = {level:g}")
        ax.annotate(
            f"{label} ({level:g})",
            xy=(timeline[-1], level),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            color=colors.get(label, "gray"),
            fontsize=10,
            fontweight="bold",
        )

    ax.set_title(f"Diễn biến mực nước trạm {ma_tram}", fontsize=style["title_size"])
    ax.set_xlabel("Thời gian", fontsize=style["label_size"])
    ax.set_ylabel("Mực nước (m)", fontsize=style["label_size"])
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(fontsize=style["legend_size"])
    ax.tick_params(axis="both", labelsize=style["tick_size"])

    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()

    fig.savefig(output_path, dpi=150)
    if show:
        plt.show()
    else:
        plt.close(fig)

    print(f"Saved plot to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sheet-url",
        default=DEFAULT_SHEET_URL,
        help="Google Sheet CSV export URL (override if needed)",
    )
    parser.add_argument(
        "--csv",
        help="Path to a local CSV file (skips Google Sheet download)",
    )
    parser.add_argument(
        "--ma-tram",
        default="553300",
        help="Mã trạm cần lọc",
    )
    parser.add_argument(
        "--output",
        default="tram_ainghia_plot.png",
        help="Đường dẫn file hình đầu ra",
    )
    parser.add_argument(
        "--mobile-output",
        help="Đường dẫn file hình cho giao diện mobile",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Hiển thị biểu đồ sau khi vẽ",
    )
    parser.add_argument(
        "--telegram-token",
        help="Telegram bot token (nếu bỏ trống sẽ đọc TELEGRAM_BOT_TOKEN)",
    )
    parser.add_argument(
        "--telegram-chat-id",
        help="Telegram chat ID (nếu bỏ trống sẽ đọc TELEGRAM_CHAT_ID)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.csv:
        csv_path = Path(args.csv).expanduser().resolve()
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        records = parse_csv_file(csv_path)
    else:
        csv_text = download_sheet_csv(args.sheet_url)
        records = parse_csv_content(csv_text)

    timeline, values = build_series(records, args.ma_tram)

    telegram_config = resolve_telegram_config(args.telegram_token, args.telegram_chat_id)
    notify_if_threshold_exceeded(timeline, values, args.ma_tram, telegram_config)

    plot_series(timeline, values, Path(args.output), args.show, args.ma_tram, "desktop")
    if args.mobile_output:
        plot_series(
            timeline,
            values,
            Path(args.mobile_output),
            False,
            args.ma_tram,
            "mobile",
        )


if __name__ == "__main__":
    main()
