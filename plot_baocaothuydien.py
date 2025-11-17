#!/usr/bin/env python3
"""Fetch hydroelectric discharge data and plot qvevugia/qvethubon time series."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    def load_dotenv(*args, **kwargs):  # type: ignore[override]
        return False

from telegram_notifier import maybe_notify

def default_today_end_iso() -> str:
    today = datetime.now(timezone.utc).date()
    end_of_day = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)
    return end_of_day.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def default_yesterday_start_iso() -> str:
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    start_of_day = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0, tzinfo=timezone.utc)
    return start_of_day.strftime("%Y-%m-%dT%H:%M:%S.000Z")


BASE_URL = "https://pctt.danang.gov.vn/DesktopModules/PCTT/api/PCTTApi/baocaothuydiens_thongke"
load_dotenv()

DEFAULT_START = os.getenv("BAOCAOTHUYDIEN_DEFAULT_START") or default_yesterday_start_iso()
DEFAULT_END = os.getenv("BAOCAOTHUYDIEN_DEFAULT_END") or default_today_end_iso()
DEFAULT_PLANT_IDS = "1,2,3,4"
MARKED_VALUE_BY_DATE = os.getenv("MARKED_VALUE_BY_DATE", "")
CACHE_DIR = Path(".cache")
CACHE_TTL = timedelta(hours=1)
CACHE_VERSION = "3"
MARKED_CACHE_PATH = CACHE_DIR / "marked_dates.json"

STYLE_PRESETS = {
    "desktop": {
        "hourly_figsize": (12, 6),
        "overlay_figsize": (12, 10),
        "title_size": 18,
        "label_size": 12,
        "tick_size": 11,
        "legend_size": 11,
        "annot_size": 10,
    },
    "mobile": {
        "hourly_figsize": (6.2, 9.5),
        "overlay_figsize": (6.2, 11.5),
        "title_size": 20,
        "label_size": 14,
        "tick_size": 13,
        "legend_size": 13,
        "annot_size": 12,
    },
}


def get_style(style_name: str) -> dict:
    return STYLE_PRESETS.get(style_name, STYLE_PRESETS["desktop"])


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_cache_key(start: str, end: str, plant_ids: str) -> str:
    digest = hashlib.sha256("|".join([start, end, plant_ids]).encode("utf-8")).hexdigest()
    return digest[:16]


def get_cache_paths(key: str) -> tuple[Path, Path, Path, Path]:
    data_path = CACHE_DIR / f"{key}.data.json"
    hourly_path = CACHE_DIR / f"{key}.hourly.png"
    overlay_path = CACHE_DIR / f"{key}.overlay.png"
    meta_path = CACHE_DIR / f"{key}.meta.json"
    return data_path, hourly_path, overlay_path, meta_path


def load_cache(key: str) -> Optional[dict[str, object]]:
    data_path, hourly_path, overlay_path, meta_path = get_cache_paths(key)
    if not meta_path.exists():
        return None

    try:
        with meta_path.open("r", encoding="utf-8") as meta_file:
            meta = json.load(meta_file)
    except json.JSONDecodeError:
        return None

    if meta.get("version") != CACHE_VERSION:
        return None

    fetched_at_raw = meta.get("fetched_at")
    if not fetched_at_raw:
        return None

    try:
        fetched_at = datetime.fromisoformat(fetched_at_raw)
    except ValueError:
        return None

    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)

    last_run = None
    last_run_raw = meta.get("last_run")
    if last_run_raw:
        try:
            last_run = datetime.fromisoformat(last_run_raw)
        except ValueError:
            last_run = None

    now_utc = datetime.now(timezone.utc)
    if now_utc - fetched_at > CACHE_TTL:
        return None

    if not data_path.exists():
        return None

    with data_path.open("r", encoding="utf-8") as data_file:
        records = json.load(data_file)

    hourly_file = hourly_path if hourly_path.exists() else None
    overlay_file = overlay_path if overlay_path.exists() else None
    return {
        "records": records,
        "hourly_path": hourly_file,
        "overlay_path": overlay_file,
        "fetched_at": fetched_at,
        "last_run": last_run,
        "params": meta.get("params", {}),
    }


def save_cache(
    records: Iterable[Dict[str, float]],
    hourly_path: Path,
    overlay_path: Path,
    key: str,
    fetched_at: datetime,
    params: dict[str, str],
    last_run: datetime,
) -> None:
    ensure_cache_dir()
    data_path, cached_hourly_path, cached_overlay_path, meta_path = get_cache_paths(key)

    records_list = list(records)

    with data_path.open("w", encoding="utf-8") as data_file:
        json.dump(records_list, data_file, ensure_ascii=False, indent=2)

    if hourly_path.exists():
        shutil.copy2(hourly_path, cached_hourly_path)

    if overlay_path.exists():
        shutil.copy2(overlay_path, cached_overlay_path)

    meta = {
        "fetched_at": fetched_at.isoformat(),
        "last_run": last_run.isoformat(),
        "params": params,
        "version": CACHE_VERSION,
    }
    with meta_path.open("w", encoding="utf-8") as meta_file:
        json.dump(meta, meta_file, ensure_ascii=False, indent=2)


def copy_cached_plot(cached_plot_path: Optional[Path], destination: Path) -> None:
    if not cached_plot_path or not cached_plot_path.exists():
        return
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached_plot_path, destination)


def show_cached_plot(image_path: Optional[Path]) -> None:
    if image_path is None:
        return
    image_path = image_path.resolve()
    if not image_path.exists():
        return
    img = plt.imread(image_path)
    plt.figure(figsize=(12, 8))
    plt.imshow(img)
    plt.axis("off")
    plt.title("Báo cáo thủy điện (cached)")
    plt.tight_layout()
    plt.show()


def build_request_url(start: str, end: str, plant_ids: str) -> str:
    """Compose the data endpoint with the provided query parameters."""
    params = {
        "ngaybatdau": start,
        "ngayketthuc": end,
        "lst_thuydien_id": plant_ids,
    }
    return f"{BASE_URL}?{urlencode(params, safe=':,')}"


def fetch_data(url: str) -> List[Dict[str, float]]:
    """Download the JSON payload from the API."""
    with urlopen(url) as response:  # nosec B310 - trusted endpoint provided by user
        if response.status != 200:
            raise RuntimeError(f"Request failed with status {response.status}")
        return json.load(response)


def parse_marked_dates(env_value: str) -> List[str]:
    """Parse comma-separated date list from MARKED_VALUE_BY_DATE."""
    if not env_value:
        return []
    return [d.strip() for d in env_value.split(",") if d.strip()]


def load_marked_cache() -> Dict[str, Tuple[float, float]]:
    """Load cached marked date maxima from disk."""
    if not MARKED_CACHE_PATH.exists():
        return {}
    try:
        with MARKED_CACHE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_marked_cache(cache: Dict[str, Tuple[float, float]]) -> None:
    """Save marked date maxima to disk."""
    ensure_cache_dir()
    with MARKED_CACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_marked_date_maxima(
    dates: List[str],
    plant_ids: str,
) -> Dict[str, Tuple[float, float]]:
    """Fetch and cache daily max for marked dates. Returns {date: (max_vu, max_thu)}."""
    cache = load_marked_cache()
    updated = False

    for date_str in dates:
        if date_str in cache:
            continue

        start_iso = f"{date_str}T00:00:00.000Z"
        end_iso = f"{date_str}T23:59:59.999Z"
        url = build_request_url(start_iso, end_iso, plant_ids)
        print(f"Fetching marked date {date_str} from API...")

        try:
            records = fetch_data(url)
        except Exception as e:
            print(f"Failed to fetch {date_str}: {e}")
            continue

        if not records:
            cache[date_str] = (0.0, 0.0)
            updated = True
            continue

        max_vu = 0.0
        max_thu = 0.0
        for record in records:
            qvu = safe_float(record.get("qvevugia"), 0.0)
            qthu = safe_float(record.get("qvethubon"), 0.0)
            if qvu > max_vu:
                max_vu = qvu
            if qthu > max_thu:
                max_thu = qthu

        cache[date_str] = (max_vu, max_thu)
        updated = True

    if updated:
        save_marked_cache(cache)

    return cache


def extract_series(records: Iterable[Dict[str, float]]):
    """Return sorted timeline and the two discharge series."""
    latest_by_time: Dict[str, Tuple[float, float]] = {}
    for record in records:
        key = record.get("thoigianxa")
        if not key:
            continue

        qvu = safe_float(record.get("qvevugia"), 0.0)
        qthu = safe_float(record.get("qvethubon"), 0.0)

        if qvu == 0.0 and qthu == 0.0:
            continue

        latest_by_time[key] = (qvu, qthu)  # keep the last record per timestamp if duplicates exist

    ordered_keys = sorted(latest_by_time.keys())
    timeline = [datetime.fromisoformat(key) for key in ordered_keys]
    qve_vugia = [latest_by_time[key][0] for key in ordered_keys]
    qve_thubon = [latest_by_time[key][1] for key in ordered_keys]
    return timeline, qve_vugia, qve_thubon


def prepare_overlay_series(
    timeline: Sequence[datetime],
    qve_vugia: Sequence[float],
    qve_thubon: Sequence[float],
) -> Tuple[Dict[str, Tuple[List[datetime], List[float]]], Dict[str, Tuple[List[datetime], List[float]]]]:
    """Organise time series per day for overlay plots by hour."""
    base_date = datetime(2000, 1, 1)
    vu_pairs: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)
    thu_pairs: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)

    for ts, vu, thu in zip(timeline, qve_vugia, qve_thubon):
        label = ts.strftime("%Y-%m-%d")
        overlay_time = datetime.combine(base_date.date(), ts.time())
        vu_pairs[label].append((overlay_time, vu))
        thu_pairs[label].append((overlay_time, thu))

    vu_buckets: Dict[str, Tuple[List[datetime], List[float]]] = {}
    thu_buckets: Dict[str, Tuple[List[datetime], List[float]]] = {}

    for label, pairs in vu_pairs.items():
        pairs.sort(key=lambda item: item[0])
        times, values = zip(*pairs)
        vu_buckets[label] = (list(times), list(values))

    for label, pairs in thu_pairs.items():
        pairs.sort(key=lambda item: item[0])
        times, values = zip(*pairs)
        thu_buckets[label] = (list(times), list(values))

    return vu_buckets, thu_buckets


def plot_series(
    timeline,
    qve_vugia,
    qve_thubon,
    vu_overlay,
    thu_overlay,
    hourly_output_path: Path,
    overlay_output_path: Path,
    show_plot: bool,
    marked_maxima: Optional[Dict[str, Tuple[float, float]]] = None,
    style_name: str = "desktop",
) -> None:
    """Produce separate hourly and overlay charts."""
    hourly_output_path = hourly_output_path.resolve()
    hourly_output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_output_path = overlay_output_path.resolve()
    overlay_output_path.parent.mkdir(parents=True, exist_ok=True)

    style = get_style(style_name)

    fig_hourly, ax_hourly = plt.subplots(figsize=style["hourly_figsize"])
    ax_hourly.plot(timeline, qve_vugia, color="tab:blue", label="Q về Vu Gia")
    ax_hourly.plot(timeline, qve_thubon, color="tab:green", label="Q về Thu Bồn")

    if timeline:
        last_time = timeline[-1]
        if qve_vugia:
            last_vu = qve_vugia[-1]
            ax_hourly.scatter(last_time, last_vu, color="tab:blue", s=50, zorder=5)
            ax_hourly.annotate(
                f"{last_vu:.1f}",
                (last_time, last_vu),
                textcoords="offset points",
                xytext=(6, 6),
                ha="left",
                color="tab:blue",
                fontsize=style["annot_size"],
            )
        if qve_thubon:
            last_thu = qve_thubon[-1]
            ax_hourly.scatter(last_time, last_thu, color="tab:green", s=50, zorder=5)
            ax_hourly.annotate(
                f"{last_thu:.1f}",
                (last_time, last_thu),
                textcoords="offset points",
                xytext=(6, -12),
                ha="left",
                color="tab:green",
                fontsize=style["annot_size"],
            )

    if marked_maxima:
        colors = ["tab:orange", "tab:red", "tab:purple", "tab:brown", "tab:pink"]
        for idx, (date_str, (max_vu, max_thu)) in enumerate(sorted(marked_maxima.items())):
            color = colors[idx % len(colors)]
            if max_vu > 0:
                ax_hourly.axhline(max_vu, color=color, linestyle="--", linewidth=1, alpha=0.7, label=f"{date_str} VG max={max_vu:.0f}")
            if max_thu > 0:
                ax_hourly.axhline(max_thu, color=color, linestyle=":", linewidth=1, alpha=0.7, label=f"{date_str} TB max={max_thu:.0f}")

    ax_hourly.set_title("Diễn biến theo giờ", fontsize=style["title_size"])
    ax_hourly.set_xlabel("Thời gian xả", fontsize=style["label_size"])
    ax_hourly.set_ylabel("Lưu lượng", fontsize=style["label_size"])
    ax_hourly.legend(fontsize=style["legend_size"])
    ax_hourly.grid(True, which="major", linestyle="--", alpha=0.5)
    ax_hourly.tick_params(axis="both", labelsize=style["tick_size"])
    ax_hourly.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    fig_hourly.autofmt_xdate()
    fig_hourly.tight_layout()
    fig_hourly.savefig(hourly_output_path, dpi=150)

    fig_overlay, axes_overlay = plt.subplots(2, 1, figsize=style["overlay_figsize"], sharex=False)

    for label in sorted(vu_overlay.keys()):
        times, values = vu_overlay[label]
        axes_overlay[0].plot(times, values, label=label)
    axes_overlay[0].set_title("Q về Vu Gia - So sánh từng ngày theo giờ", fontsize=style["title_size"])
    axes_overlay[0].set_xlabel("Thời gian xả", fontsize=style["label_size"])
    axes_overlay[0].set_ylabel("Lưu lượng", fontsize=style["label_size"])
    axes_overlay[0].legend(fontsize=style["legend_size"])
    axes_overlay[0].grid(True, which="major", linestyle="--", alpha=0.5)
    axes_overlay[0].tick_params(axis="both", labelsize=style["tick_size"])
    axes_overlay[0].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    for label in sorted(thu_overlay.keys()):
        times, values = thu_overlay[label]
        axes_overlay[1].plot(times, values, label=label)
    axes_overlay[1].set_title("Q về Thu Bồn - So sánh từng ngày theo giờ", fontsize=style["title_size"])
    axes_overlay[1].set_xlabel("Thời gian xả", fontsize=style["label_size"])
    axes_overlay[1].set_ylabel("Lưu lượng", fontsize=style["label_size"])
    axes_overlay[1].legend(fontsize=style["legend_size"])
    axes_overlay[1].grid(True, which="major", linestyle="--", alpha=0.5)
    axes_overlay[1].tick_params(axis="both", labelsize=style["tick_size"])
    axes_overlay[1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    fig_overlay.suptitle("Báo cáo thủy điện", fontsize=style["title_size"])
    fig_overlay.tight_layout(rect=(0, 0, 1, 0.95))
    fig_overlay.savefig(overlay_output_path, dpi=150)

    if show_plot:
        plt.show()
    else:
        plt.close(fig_hourly)
        plt.close(fig_overlay)

    print(f"Saved hourly plot to {hourly_output_path}")
    print(f"Saved overlay plot to {overlay_output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START, help="ngaybatdau query param")
    parser.add_argument("--end", default=DEFAULT_END, help="ngayketthuc query param")
    print("start", DEFAULT_START)
    print("end", DEFAULT_END)
    parser.add_argument(
        "--plant-ids",
        default=DEFAULT_PLANT_IDS,
        help="Comma-separated lst_thuydien_id query param",
    )
    parser.add_argument(
        "--output",
        default="baocaothuydien_plot.png",
        help="Path to save the generated plot",
    )
    parser.add_argument(
        "--mobile-output",
        help="Path to save the mobile-friendly hourly plot",
    )
    parser.add_argument(
        "--mobile-overlay-output",
        help="Path to save the mobile-friendly overlay plot",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the graph window after saving",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(CACHE_DIR),
        help="Directory for cached payloads and plots",
    )
    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=int(CACHE_TTL.total_seconds() // 60),
        help="Cache freshness window in minutes",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass cache and always call the API",
    )
    return parser.parse_args()


def main() -> None:
    print("-" * 80)
    args = parse_args()
    global CACHE_DIR, CACHE_TTL
    CACHE_DIR = Path(args.cache_dir).expanduser().resolve()
    CACHE_TTL = timedelta(minutes=args.cache_ttl)

    params = {
        "start": args.start,
        "end": args.end,
        "plant_ids": args.plant_ids,
    }
    cache_key = build_cache_key(args.start, args.end, args.plant_ids)

    cache_info = None
    if not args.force_refresh:
        cache_info = load_cache(cache_key)

    records: List[Dict[str, float]]
    fetched_at: datetime

    if cache_info is not None:
        records = list(cache_info["records"])
        fetched_at = cache_info["fetched_at"]
        last_run = cache_info.get("last_run") or datetime.now(timezone.utc)
        print(
            "Using cached data fetched at"
            f" {fetched_at.astimezone(timezone.utc).isoformat()}"
        )
        cached_hourly = cache_info.get("hourly_path")
        cached_overlay = cache_info.get("overlay_path")
    else:
        ensure_cache_dir()
        request_url = build_request_url(args.start, args.end, args.plant_ids)
        print(f"Fetching data from: {request_url}")
        records = fetch_data(request_url)

        if not records:
            raise ValueError("No data returned from the API")

        fetched_at = datetime.now(timezone.utc)
        last_run = fetched_at
        cached_hourly = None
        cached_overlay = None

    timeline, qve_vugia, qve_thubon = extract_series(records)
    vu_overlay, thu_overlay = prepare_overlay_series(timeline, qve_vugia, qve_thubon)

    marked_dates = parse_marked_dates(MARKED_VALUE_BY_DATE)
    marked_maxima = fetch_marked_date_maxima(marked_dates, args.plant_ids) if marked_dates else {}

    hourly_path = Path(args.output)
    overlay_path = hourly_path.with_name(hourly_path.stem + "_overlay" + hourly_path.suffix)
    mobile_hourly_path = Path(args.mobile_output).resolve() if args.mobile_output else None
    if args.mobile_overlay_output:
        mobile_overlay_path = Path(args.mobile_overlay_output).resolve()
    elif mobile_hourly_path:
        mobile_overlay_path = mobile_hourly_path.with_name(
            mobile_hourly_path.stem + "_overlay" + mobile_hourly_path.suffix
        )
    else:
        mobile_overlay_path = None

    if cache_info is not None:
        if cached_hourly and cached_overlay:
            copy_cached_plot(cached_hourly, hourly_path)
            copy_cached_plot(cached_overlay, overlay_path)
            if args.show:
                show_cached_plot(hourly_path)
                show_cached_plot(overlay_path)
    else:
        plot_series(
            timeline,
            qve_vugia,
            qve_thubon,
            vu_overlay,
            thu_overlay,
            hourly_path,
            overlay_path,
            args.show,
            marked_maxima,
            "desktop",
        )

    if mobile_hourly_path and mobile_overlay_path:
        plot_series(
            timeline,
            qve_vugia,
            qve_thubon,
            vu_overlay,
            thu_overlay,
            mobile_hourly_path,
            mobile_overlay_path,
            False,
            marked_maxima,
            "mobile",
        )

    readings = []
    if timeline:
        latest_timestamp = timeline[-1].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
        readings.append(("Q về Vu Gia", qve_vugia[-1], latest_timestamp))
        readings.append(("Q về Thu Bồn", qve_thubon[-1], latest_timestamp))
    maybe_notify(readings)

    now_utc = datetime.now(timezone.utc)
    save_cache(records, hourly_path, overlay_path, cache_key, fetched_at, params, now_utc)


if __name__ == "__main__":
    main()
