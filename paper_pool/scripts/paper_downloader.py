from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


APP_NAME = "paper_downloader"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHARED_CONFIG_PATH = PROJECT_ROOT / "config" / "paper_downloader.config.json"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "paper_downloader.local.json"
DEFAULT_STATE_PATH = PROJECT_ROOT / "state" / "paper_downloader.state.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "paper_downloader.report.csv"
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "paper"
DEFAULT_PDF_URL_TEMPLATE = (
    "{article_url}/pdfft?isDTMRedir=true&download=true"
)


DEFAULT_CONFIG: dict[str, Any] = {
    "pdf_url_template": DEFAULT_PDF_URL_TEMPLATE,
    "download_dir": "paper",
    "filename_template": "{year}_{first_author}_{short_title}_{doi_suffix}.pdf",
    "timing": {
        "page_wait_seconds": 4,
        "view_pdf_wait_seconds": 4,
        "save_dialog_wait_seconds": 1,
        "download_timeout_seconds": 30,
        "min_delay_seconds": 5,
        "max_delay_seconds": 12,
        "batch_limit": 20,
        "max_consecutive_failures": 2,
    },
    "safety": {
        "manual_retry_after_failure": False,
        "max_attempts_per_article": 2,
        "close_tab_after_article": True,
        "start_chrome_if_missing": False,
        "save_action": "paste_path_enter",
        "click_save_button": False,
        "require_user_access_notice": True,
        "cloudflare_wait_seconds": 300,
        "cloudflare_poll_seconds": 3,
    },
    "vision": {
        "enabled": True,
        "template_dir": "user/screensnap",
        "view_pdf_template": "user/screensnap/view_pdf.jpg",
        "view_pdf_full_window": True,
        "download_template": "user/screensnap/download.png",
        "download_full_window": True,
        "save_template": "user/screensnap/save.png",
        "save_full_screen": True,
        "cloudflare_template": "user/screensnap/Cloudflare.png",
        "cloudflare_match_threshold": 0.82,
        "template_size": 32,
        "search_width": 260,
        "search_height": 180,
        "match_threshold": 0.88,
        "download_match_threshold": 0.92,
        "save_match_threshold": 0.86,
        "scales": [0.7, 0.85, 1.0, 1.15, 1.3, 1.5],
    },
}


RIS_TAG_RE = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")
PII_RE = re.compile(r"/pii/([^/?#]+)", re.IGNORECASE)
FORBIDDEN_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SPACE_RE = re.compile(r"\s+")


def safe_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


@dataclass(frozen=True)
class Article:
    index: int
    title: str
    authors: list[str]
    journal: str
    year: str
    doi: str
    url: str
    pii: str

    @property
    def key(self) -> str:
        if self.doi:
            return self.doi.lower()
        if self.pii:
            return self.pii
        if self.url:
            return self.url
        return f"record-{self.index}"


def read_text_with_fallback(path: Path) -> str:
    encodings = ("utf-8-sig", "utf-8", "gb18030", "cp1252")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeError(f"无法读取 {path}: {last_error}")


def resolve_project_path(value: str | Path, base_dir: Path = PROJECT_ROOT) -> Path:
    raw = os.path.expandvars(str(value)).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def parse_ris(path: Path) -> list[Article]:
    text = read_text_with_fallback(path)
    raw_records: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    current_tag: str | None = None

    def finish_record() -> None:
        nonlocal current, current_tag
        if current:
            raw_records.append(current)
        current = {}
        current_tag = None

    for line in text.splitlines():
        match = RIS_TAG_RE.match(line)
        if match:
            tag, value = match.group(1), match.group(2).strip()
            if tag == "TY" and current:
                finish_record()
            if tag == "ER":
                finish_record()
                continue
            current.setdefault(tag, []).append(value)
            current_tag = tag
            continue

        if current_tag and line.strip():
            current[current_tag][-1] = f"{current[current_tag][-1]} {line.strip()}"

    finish_record()

    articles: list[Article] = []
    for idx, record in enumerate(raw_records, start=1):
        url = first(record, "UR")
        articles.append(
            Article(
                index=idx,
                title=first(record, "TI"),
                authors=record.get("AU", []),
                journal=first(record, "T2") or first(record, "J2"),
                year=first(record, "PY") or extract_year(first(record, "DA")),
                doi=first(record, "DO"),
                url=url,
                pii=extract_pii(url),
            )
        )
    return articles


def first(record: dict[str, list[str]], tag: str) -> str:
    values = record.get(tag) or []
    return values[0].strip() if values else ""


def extract_year(value: str) -> str:
    match = re.search(r"\b(19|20)\d{2}\b", value or "")
    return match.group(0) if match else ""


def extract_pii(url: str) -> str:
    match = PII_RE.search(url or "")
    return match.group(1) if match else ""


def load_config(path: Path) -> dict[str, Any]:
    config = deep_copy(DEFAULT_CONFIG)
    if path != SHARED_CONFIG_PATH and SHARED_CONFIG_PATH.exists():
        loaded = json.loads(SHARED_CONFIG_PATH.read_text(encoding="utf-8"))
        deep_update(config, loaded)
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        deep_update(config, loaded)
    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, dict)
        ):
            deep_update(target[key], value)
        else:
            target[key] = value


def article_page_url(article: Article) -> str:
    if article.url:
        return article.url.rstrip("/")
    if article.pii:
        return f"https://www.sciencedirect.com/science/article/pii/{article.pii}"
    if article.doi:
        return f"https://doi.org/{article.doi}"
    return ""


def build_pdf_url(article: Article, template: str) -> str:
    page_url = article_page_url(article)
    if not page_url:
        return ""
    data = article_template_data(article)
    data["article_url"] = page_url
    data["doi_url"] = f"https://doi.org/{article.doi}" if article.doi else ""
    return template.format(**data)


def article_template_data(article: Article) -> dict[str, str]:
    first_author = author_family_name(article.authors[0]) if article.authors else "unknown"
    doi_suffix = article.doi.rsplit("/", 1)[-1] if article.doi else article.pii or str(article.index)
    return {
        "index": str(article.index),
        "title": article.title or "untitled",
        "short_title": shorten_filename_part(article.title or "untitled", 80),
        "first_author": first_author,
        "year": article.year or "unknown-year",
        "journal": article.journal or "unknown-journal",
        "doi": article.doi or "",
        "doi_suffix": doi_suffix,
        "pii": article.pii or "",
    }


def author_family_name(author: str) -> str:
    author = author.strip()
    if not author:
        return "unknown"
    if "," in author:
        return author.split(",", 1)[0].strip() or "unknown"
    return author.split()[0]


def shorten_filename_part(value: str, max_chars: int) -> str:
    value = sanitize_filename(value, max_chars=max_chars)
    return value or "untitled"


def sanitize_filename(value: str, max_chars: int = 180) -> str:
    value = FORBIDDEN_FILENAME_CHARS.sub("_", value)
    value = SPACE_RE.sub(" ", value).strip(" ._")
    if len(value) > max_chars:
        value = value[:max_chars].rstrip(" ._")
    return value or "untitled"


def build_target_filename(article: Article, template: str) -> str:
    data = {
        key: sanitize_filename(value, max_chars=120)
        for key, value in article_template_data(article).items()
    }
    filename = template.format(**data)
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    return sanitize_filename(filename, max_chars=220)


def target_pdf_path(download_dir: Path, article: Article, filename_template: str) -> Path:
    return download_dir / build_target_filename(article, filename_template)


def find_existing_pdf(
    download_dir: Path,
    article: Article,
    filename_template: str,
) -> Path | None:
    expected = target_pdf_path(download_dir, article, filename_template)
    if expected.exists() and expected.is_file():
        return expected
    return None


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for counter in range(2, 1000):
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{stem} ({timestamp}){suffix}")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"items": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_item_state(
    state_path: Path,
    state: dict[str, Any],
    article: Article,
    status: str,
    **extra: Any,
) -> None:
    items = state.setdefault("items", {})
    existing = items.get(article.key, {})
    attempts = int(existing.get("attempts", 0)) + (1 if status == "running" else 0)
    items[article.key] = {
        **existing,
        "index": article.index,
        "title": article.title,
        "doi": article.doi,
        "url": article.url,
        "pii": article.pii,
        "status": status,
        "attempts": attempts,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **extra,
    }
    save_state(state_path, state)


def write_report(
    report_path: Path,
    articles: list[Article],
    state: dict[str, Any],
    download_dir: Path,
    filename_template: str,
) -> None:
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    items = state.get("items", {})
    for article in articles:
        item = items.get(article.key, {})
        expected = target_pdf_path(download_dir, article, filename_template)
        file_path = item.get("file") or (str(expected) if expected.exists() else "")
        status = item.get("status", "pending")
        error = item.get("error", "")
        if expected.exists():
            status = "success"
            file_path = str(expected)
            error = ""
        counts[status] = counts.get(status, 0) + 1
        rows.append(
            {
                "index": article.index,
                "status": status,
                "attempts": item.get("attempts", 0),
                "doi": article.doi,
                "pii": article.pii,
                "title": article.title,
                "file": file_path,
                "error": error,
                "updated_at": item.get("updated_at", ""),
                "page_url": item.get("page_url") or article_page_url(article),
            }
        )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "index",
                "status",
                "attempts",
                "doi",
                "pii",
                "title",
                "file",
                "error",
                "updated_at",
                "page_url",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    print(f"统计表已生成: {report_path}")
    print(f"统计: {summary}")


def require_gui_deps() -> tuple[Any, Any]:
    missing: list[str] = []
    try:
        import pyautogui  # type: ignore
    except ImportError:
        pyautogui = None
        missing.append("pyautogui")

    try:
        from pywinauto import Desktop  # type: ignore
    except ImportError:
        Desktop = None
        missing.append("pywinauto")

    if missing:
        joined = " ".join(missing)
        raise RuntimeError(
            "缺少桌面自动化依赖: "
            f"{joined}\n请先运行: py -m pip install -r requirements.txt"
        )
    return pyautogui, Desktop


def find_chrome_window(Desktop: Any) -> Any | None:
    for backend in ("uia", "win32"):
        try:
            desktop = Desktop(backend=backend)
            windows = desktop.windows()
        except Exception:
            continue

        candidates = []
        for window in windows:
            try:
                title = window.window_text()
                if not title:
                    continue
                if "chrome" in title.lower() or "sciencedirect" in title.lower():
                    candidates.append(window)
            except Exception:
                continue

        visible = []
        for window in candidates:
            try:
                if window.is_visible() and not window.is_minimized():
                    visible.append(window)
            except Exception:
                visible.append(window)
        if visible:
            return visible[0]
        if candidates:
            return candidates[0]
    return None


def start_chrome_default_profile() -> None:
    subprocess.Popen(
        ["cmd", "/c", "start", "", "chrome", "--new-window", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def activate_chrome(Desktop: Any, start_if_missing: bool = False) -> Any | None:
    window = find_chrome_window(Desktop)
    if window is None and start_if_missing:
        print("未找到 Chrome，正在用默认用户资料启动 Chrome...")
        start_chrome_default_profile()
        time.sleep(3)
        window = find_chrome_window(Desktop)
    if window is None:
        return None
    try:
        if window.is_minimized():
            window.restore()
    except Exception:
        pass
    try:
        window.set_focus()
    except Exception:
        pass
    time.sleep(0.4)
    return window


def window_rect(window: Any | None) -> dict[str, int] | None:
    if window is None:
        return None
    try:
        rect = window.rectangle()
        return {
            "left": int(rect.left),
            "top": int(rect.top),
            "right": int(rect.right),
            "bottom": int(rect.bottom),
            "width": int(rect.right - rect.left),
            "height": int(rect.bottom - rect.top),
        }
    except Exception:
        return None


def wait_for_stable_mouse(
    pyautogui: Any,
    hold_seconds: float,
    tolerance_px: int,
) -> tuple[int, int]:
    print(f"请移动鼠标到目标按钮上，保持不动 {hold_seconds:g} 秒。")
    last_pos = pyautogui.position()
    stable_since = time.monotonic()
    while True:
        time.sleep(0.1)
        pos = pyautogui.position()
        if (
            abs(pos.x - last_pos.x) <= tolerance_px
            and abs(pos.y - last_pos.y) <= tolerance_px
        ):
            if time.monotonic() - stable_since >= hold_seconds:
                return int(pos.x), int(pos.y)
        else:
            last_pos = pos
            stable_since = time.monotonic()


def clamp_region(
    left: int,
    top: int,
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int, int, int]:
    left = max(0, min(left, screen_width - 1))
    top = max(0, min(top, screen_height - 1))
    width = max(1, min(width, screen_width - left))
    height = max(1, min(height, screen_height - top))
    return left, top, width, height


def image_to_gray_samples(image: Any) -> tuple[list[int], int, int]:
    gray = image.convert("L")
    width, height = gray.size
    return list(gray.getdata()), width, height


def resolve_template_path(path_value: str) -> Path:
    return resolve_project_path(path_value)


def configured_template_path(config: dict[str, Any], key: str) -> Path | None:
    value = (config.get("vision") or {}).get(key)
    if not value:
        return None
    return resolve_template_path(str(value))


def required_vision_template_errors(config: dict[str, Any], save_action: str) -> list[str]:
    vision = config.get("vision") or {}
    if not vision.get("enabled", True):
        return ["图像识别已关闭；当前运行模式需要启用 vision.enabled"]

    required = [
        ("view_pdf_template", "View PDF 按钮"),
        ("download_template", "下载按钮"),
    ]
    if save_action == "click":
        required.append(("save_template", "保存按钮"))

    errors: list[str] = []
    for key, label in required:
        path = configured_template_path(config, key)
        if path is None:
            errors.append(f"{label}模板未配置: vision.{key}")
        elif not path.exists():
            errors.append(f"{label}模板不存在: {path}")
    return errors


def capture_configured_template(
    label: str,
    template_key: str,
    pyautogui: Any,
    config: dict[str, Any],
    hold_seconds: float,
    tolerance_px: int,
) -> Path:
    target_path = configured_template_path(config, template_key)
    if target_path is None:
        raise RuntimeError(f"缺少模板路径配置: vision.{template_key}")

    print()
    print(f"采集 {label} 模板")
    x, y = wait_for_stable_mouse(pyautogui, hold_seconds, tolerance_px)
    vision = config.get("vision") or {}
    size = int(vision.get("template_size", 48))
    screen_width, screen_height = pyautogui.size()
    left, top, width, height = clamp_region(
        x - size // 2,
        y - size // 2,
        size,
        size,
        int(screen_width),
        int(screen_height),
    )
    image = pyautogui.screenshot(region=(left, top, width, height))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(target_path)
    print(f"已保存 {label} 模板: {target_path}")
    return target_path


def similarity_score(
    search_pixels: list[int],
    search_width: int,
    template_pixels: list[int],
    template_width: int,
    template_height: int,
    x: int,
    y: int,
) -> float:
    total_diff = 0
    count = template_width * template_height
    for ty in range(template_height):
        search_offset = (y + ty) * search_width + x
        template_offset = ty * template_width
        for tx in range(template_width):
            total_diff += abs(
                search_pixels[search_offset + tx]
                - template_pixels[template_offset + tx]
            )
    return 1.0 - (total_diff / (count * 255))


def locate_image_in_region_cv(
    pyautogui: Any,
    region: tuple[int, int, int, int],
    template_path: Path,
    scales: list[float],
    threshold: float,
) -> tuple[int, int, float, bool] | None:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        from PIL import ImageGrab  # type: ignore

        region_left, region_top, region_width, region_height = region
        bbox = (
            region_left,
            region_top,
            region_left + region_width,
            region_top + region_height,
        )
        screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
        screen_rgb = np.array(screenshot)
        screen_gray = cv2.cvtColor(screen_rgb, cv2.COLOR_RGB2GRAY)
        template_gray = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
        if template_gray is None:
            return None

        best: tuple[int, int, float] | None = None
        for scale in scales:
            scaled_width = max(8, int(template_gray.shape[1] * scale))
            scaled_height = max(8, int(template_gray.shape[0] * scale))
            if scaled_width > region_width or scaled_height > region_height:
                continue
            scaled = cv2.resize(
                template_gray,
                (scaled_width, scaled_height),
                interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
            )
            result = cv2.matchTemplate(screen_gray, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_value, _, max_location = cv2.minMaxLoc(result)
            score = float(max_value)
            if best is None or score > best[2]:
                x = region_left + int(max_location[0]) + scaled_width // 2
                y = region_top + int(max_location[1]) + scaled_height // 2
                best = (x, y, score)

        if best and best[2] >= threshold:
            return best[0], best[1], best[2], True
        if best:
            return best[0], best[1], best[2], False
        return None
    except Exception as exc:
        print(f"OpenCV 图像识别失败: {exc}")
        return None


def locate_named_template_in_chrome(
    template_path: Path,
    Desktop: Any,
    pyautogui: Any,
    config: dict[str, Any],
    threshold: float | None = None,
) -> tuple[int, int, float, bool] | None:
    if not template_path.exists():
        return None
    chrome = find_chrome_window(Desktop)
    rect = window_rect(chrome)
    if not rect:
        return None
    vision = config.get("vision", {})
    scales = [float(scale) for scale in vision.get("scales", [1.0])]
    threshold = float(threshold if threshold is not None else vision.get("match_threshold", 0.88))
    region = (
        rect["left"],
        rect["top"],
        max(1, rect["width"]),
        max(1, rect["height"]),
    )
    return locate_image_in_region_cv(
        pyautogui,
        region,
        template_path,
        scales,
        threshold,
    )


def virtual_screen_region() -> tuple[int, int, int, int]:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        left = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
        top = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
        width = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
        height = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
        return left, top, max(1, width), max(1, height)
    except Exception:
        return 0, 0, 3000, 2000


def locate_named_template_on_screen(
    template_path: Path,
    pyautogui: Any,
    config: dict[str, Any],
    threshold: float | None = None,
) -> tuple[int, int, float, bool] | None:
    if not template_path.exists():
        return None
    vision = config.get("vision", {})
    scales = [float(scale) for scale in vision.get("scales", [1.0])]
    threshold = float(threshold if threshold is not None else vision.get("match_threshold", 0.88))
    return locate_image_in_region_cv(
        pyautogui,
        virtual_screen_region(),
        template_path,
        scales,
        threshold,
    )


def click_save_confirmation_if_visible(pyautogui: Any, config: dict[str, Any]) -> bool:
    vision = config.get("vision", {})
    template_value = vision.get("save_template")
    if not template_value:
        return False
    template_path = resolve_template_path(str(template_value))
    result = locate_named_template_on_screen(
        template_path,
        pyautogui,
        config,
        threshold=float(vision.get("save_match_threshold", 0.9)),
    )
    if result is None:
        print("保存按钮模板没有得到匹配结果，回退按 Enter")
        return False
    x, y, score, matched = result
    if not matched:
        print(f"保存按钮最高相似度 {score:.3f}，低于阈值，回退按 Enter")
        return False
    print(f"保存按钮模板识别命中: ({x}, {y}), 相似度 {score:.3f}")
    click_point(pyautogui, x, y)
    return True


def locate_save_button(pyautogui: Any, config: dict[str, Any]) -> tuple[int, int, float] | None:
    vision = config.get("vision", {})
    template_value = vision.get("save_template")
    if not template_value:
        return None
    template_path = resolve_template_path(str(template_value))
    result = locate_named_template_on_screen(
        template_path,
        pyautogui,
        config,
        threshold=float(vision.get("save_match_threshold", 0.9)),
    )
    if result is None:
        return None
    x, y, score, matched = result
    if matched:
        return x, y, score
    return None


def locate_view_pdf_button(pyautogui: Any, Desktop: Any, config: dict[str, Any]) -> tuple[int, int, float] | None:
    vision = config.get("vision", {})
    template_value = vision.get("view_pdf_template")
    if not template_value:
        return None
    result = locate_named_template_in_chrome(
        resolve_template_path(str(template_value)),
        Desktop,
        pyautogui,
        config,
        threshold=float(vision.get("match_threshold", 0.88)),
    )
    if result is None:
        return None
    x, y, score, matched = result
    if matched:
        return x, y, score
    return None


def locate_download_button(pyautogui: Any, Desktop: Any, config: dict[str, Any]) -> tuple[int, int, float] | None:
    vision = config.get("vision", {})
    template_value = vision.get("download_template")
    if not template_value:
        return None
    result = locate_named_template_in_chrome(
        resolve_template_path(str(template_value)),
        Desktop,
        pyautogui,
        config,
        threshold=float(vision.get("download_match_threshold", 0.92)),
    )
    if result is None:
        return None
    x, y, score, matched = result
    if matched:
        return x, y, score
    return None


def detect_cloudflare_challenge(pyautogui: Any, config: dict[str, Any]) -> tuple[int, int, float, Path] | None:
    vision = config.get("vision", {})
    template_value = vision.get("cloudflare_template")
    if not template_value:
        return None
    template_path = resolve_template_path(str(template_value))
    result = locate_named_template_on_screen(
        template_path,
        pyautogui,
        config,
        threshold=float(vision.get("cloudflare_match_threshold", 0.82)),
    )
    if result is None:
        return None
    x, y, score, matched = result
    if matched:
        return x, y, score, template_path
    return None


def move_mouse_near_cloudflare_checkbox(
    pyautogui: Any,
    match: tuple[int, int, float, Path],
) -> None:
    x, y, _, template_path = match
    try:
        from PIL import Image  # type: ignore

        with Image.open(template_path) as image:
            width, height = image.size
        checkbox_x = x - int(width * 0.43)
        checkbox_y = y
        pyautogui.moveTo(checkbox_x, checkbox_y, duration=0.2)
        print(f"已把鼠标移动到验证框附近: ({checkbox_x}, {checkbox_y})，请手动点击。")
    except Exception as exc:
        print(f"移动到验证框附近失败，已停留等待你手动处理: {exc}")


def wait_for_cloudflare_if_present(pyautogui: Any, config: dict[str, Any]) -> None:
    safety = config.get("safety", {})
    wait_seconds = int(safety.get("cloudflare_wait_seconds", 300))
    poll_seconds = max(1, int(safety.get("cloudflare_poll_seconds", 3)))
    match = detect_cloudflare_challenge(pyautogui, config)
    if not match:
        return

    x, y, score, _ = match
    print()
    print(f"检测到 Cloudflare 验证: ({x}, {y}), 相似度 {score:.3f}")
    print("请手动完成验证。程序不会自动点击验证框；验证消失后会自动继续。")
    move_mouse_near_cloudflare_checkbox(pyautogui, match)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_seconds)
        if not detect_cloudflare_challenge(pyautogui, config):
            print("Cloudflare 验证已消失，继续。")
            return
        remaining = max(0, int(deadline - time.monotonic()))
        print(f"仍在等待 Cloudflare 验证完成，剩余 {remaining} 秒...")

    raise RuntimeError(f"Cloudflare 验证在 {wait_seconds} 秒内未完成")


def close_current_tab(pyautogui: Any, enabled: bool = True) -> None:
    if not enabled:
        return
    try:
        pyautogui.press("esc")
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "w")
        time.sleep(0.4)
        print("已关闭当前标签页，减少打开的文献页面。")
    except Exception as exc:
        print(f"关闭当前标签页失败，继续运行: {exc}")


def navigate_to_url(pyautogui: Any, url: str) -> None:
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.2)
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(url)
        pyautogui.hotkey("ctrl", "v")
    except Exception:
        pyautogui.write(url, interval=0)
    pyautogui.press("enter")


def paste_text(pyautogui: Any, text: str) -> bool:
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return True
    except Exception:
        return False


def click_point(pyautogui: Any, x: int, y: int) -> None:
    pyautogui.moveTo(x, y, duration=0.15)
    pyautogui.click()


def snapshot_download_dir(download_dir: Path) -> dict[str, tuple[float, int]]:
    snapshot: dict[str, tuple[float, int]] = {}
    if not download_dir.exists():
        return snapshot
    for path in download_dir.iterdir():
        if path.is_file():
            try:
                stat = path.stat()
                snapshot[path.name] = (stat.st_mtime, stat.st_size)
            except OSError:
                continue
    return snapshot


def wait_for_completed_pdf(
    download_dir: Path,
    before: dict[str, tuple[float, int]],
    started_at: float,
    timeout_seconds: int,
    expected_path: Path | None = None,
    verbose: bool = True,
) -> Path | None:
    deadline = time.monotonic() + timeout_seconds
    last_path: Path | None = None
    last_size = -1
    stable_since = time.monotonic()
    next_progress = time.monotonic() + 5

    if verbose:
        print(f"等待 PDF 下载完成，最多 {timeout_seconds} 秒...")

    while time.monotonic() < deadline:
        if expected_path and expected_path.exists() and expected_path.is_file():
            temp_path = expected_path.with_suffix(expected_path.suffix + ".crdownload")
            if not temp_path.exists():
                return expected_path

        candidates: list[Path] = []
        for path in download_dir.glob("*.pdf"):
            try:
                stat = path.stat()
            except OSError:
                continue
            before_stat = before.get(path.name)
            is_new = before_stat is None
            is_changed = before_stat is not None and (
                stat.st_mtime > before_stat[0] + 0.5 or stat.st_size != before_stat[1]
            )
            is_recent = stat.st_mtime >= started_at - 2
            if is_new or is_changed or is_recent:
                candidates.append(path)

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            candidate = candidates[0]
            try:
                size = candidate.stat().st_size
            except OSError:
                time.sleep(1)
                continue
            if candidate == last_path and size == last_size:
                if time.monotonic() - stable_since >= 2:
                    temp_files = list(download_dir.glob("*.crdownload"))
                    if not temp_files:
                        return candidate
            else:
                last_path = candidate
                last_size = size
                stable_since = time.monotonic()

        now = time.monotonic()
        if verbose and now >= next_progress:
            remaining = max(0, int(deadline - now))
            temp_files = list(download_dir.glob("*.crdownload"))
            if expected_path and expected_path.exists():
                print(f"检测到目标文件，等待它稳定: {expected_path.name}")
            elif last_path:
                print(f"仍在等待 PDF 完成，最近文件: {last_path.name} ({last_size} bytes)，剩余 {remaining} 秒")
            elif temp_files:
                names = ", ".join(path.name for path in temp_files[:3])
                print(f"检测到下载临时文件: {names}，剩余 {remaining} 秒")
            else:
                print(f"还没有在 {download_dir} 检测到新的 PDF，剩余 {remaining} 秒")
            next_progress = now + 5

        time.sleep(1)
    return None


def process_article_observe_loop(
    article: Article,
    page_url: str,
    expected_path: Path,
    download_dir: Path,
    before: dict[str, tuple[float, int]],
    started_at: float,
    config: dict[str, Any],
    pyautogui: Any,
    Desktop: Any,
    save_action: str,
) -> Path:
    timing = config["timing"]
    action_timeout = int(timing["download_timeout_seconds"])
    deadline = time.monotonic() + action_timeout
    last_action_at: dict[str, float] = {}
    view_clicks = 0
    download_clicks = 0
    save_handled = False

    def can_do(action: str, cooldown: float) -> bool:
        return time.monotonic() - last_action_at.get(action, 0) >= cooldown

    def mark(action: str) -> None:
        nonlocal deadline
        last_action_at[action] = time.monotonic()
        deadline = max(deadline, last_action_at[action] + action_timeout)

    activate_chrome(Desktop)
    navigate_to_url(pyautogui, page_url)
    print("进入观察循环：会根据当前屏幕上的按钮/验证/保存框决定下一步。")

    while time.monotonic() < deadline:
        existing = find_existing_pdf(download_dir, article, config["filename_template"])
        if existing:
            return existing

        completed = wait_for_completed_pdf(
            download_dir,
            before,
            started_at,
            1,
            expected_path=expected_path,
            verbose=False,
        )
        if completed:
            return completed

        cf_match = detect_cloudflare_challenge(pyautogui, config)
        if cf_match:
            wait_for_cloudflare_if_present(pyautogui, config)
            mark("cloudflare")
            continue

        save_match = locate_save_button(pyautogui, config)
        if save_match and not save_handled and can_do("save", 2):
            x, y, score = save_match
            print(f"观察到保存按钮: ({x}, {y}), 相似度 {score:.3f}")
            if save_action == "paste_path_enter":
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.1)
                if not paste_text(pyautogui, str(expected_path)):
                    raise RuntimeError("无法写入剪贴板，请安装/检查 pyperclip")
                time.sleep(0.2)
                click_point(pyautogui, x, y)
            elif save_action == "click":
                click_point(pyautogui, x, y)
            elif save_action == "enter":
                pyautogui.press("enter")
            save_handled = True
            mark("save")
            time.sleep(0.5)
            continue

        download_match = locate_download_button(pyautogui, Desktop, config)
        if download_match and download_clicks < 1 and can_do("download", 3):
            x, y, score = download_match
            print(f"观察到下载按钮: ({x}, {y}), 相似度 {score:.3f}")
            pyautogui.press("esc")
            time.sleep(0.1)
            click_point(pyautogui, x, y)
            download_clicks += 1
            mark("download")
            time.sleep(float(timing["save_dialog_wait_seconds"]))
            continue

        view_match = locate_view_pdf_button(pyautogui, Desktop, config)
        if view_match and view_clicks < 1 and can_do("view_pdf", 3):
            x, y, score = view_match
            print(f"观察到 View PDF: ({x}, {y}), 相似度 {score:.3f}")
            pyautogui.press("esc")
            time.sleep(0.1)
            click_point(pyautogui, x, y)
            view_clicks += 1
            mark("view_pdf")
            time.sleep(float(timing["view_pdf_wait_seconds"]))
            continue

        remaining = max(0, int(deadline - time.monotonic()))
        print(f"未观察到可执行动作，继续等待，剩余 {remaining} 秒...")
        time.sleep(1)

    raise RuntimeError(f"{int(timing['download_timeout_seconds'])} 秒内没有完成本篇下载")


def rename_pdf(path: Path, article: Article, filename_template: str) -> Path:
    target_path = path.with_name(build_target_filename(article, filename_template))
    if path.resolve() == target_path.resolve():
        return path
    target_path = unique_path(target_path)
    path.rename(target_path)
    return target_path


def sleep_random_delay(min_seconds: int, max_seconds: int) -> None:
    if max_seconds <= 0:
        return
    if min_seconds < 0:
        min_seconds = 0
    if max_seconds < min_seconds:
        max_seconds = min_seconds
    delay = random.uniform(min_seconds, max_seconds)
    print(f"等待 {delay:.1f} 秒后继续...")
    time.sleep(delay)


def command_preview(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    articles = parse_ris(args.ris)
    print(f"RIS: {args.ris}")
    print(f"记录数: {len(articles)}")
    print(f"候选 PDF URL 模板: {config['pdf_url_template']}")
    print()
    for article in articles[: args.limit]:
        page_url = article_page_url(article)
        pdf_url = build_pdf_url(article, config["pdf_url_template"])
        filename = build_target_filename(article, config["filename_template"])
        print(f"[{article.index}] {article.title}")
        print(f"    DOI: {article.doi or '-'}")
        print(f"    PII: {article.pii or '-'}")
        print(f"    文章页: {page_url or '-'}")
        print(f"    候选 PDF: {pdf_url or '-'}")
        print(f"    文件名: {filename}")
    if len(articles) > args.limit:
        print(f"... 还有 {len(articles) - args.limit} 条未显示")
    return 0


def command_init_config(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.download_dir:
        config["download_dir"] = str(args.download_dir)
    save_config(args.config, config)
    print(f"已写入配置: {args.config}")
    return 0


def command_calibrate(args: argparse.Namespace) -> int:
    pyautogui, Desktop = require_gui_deps()
    config = load_config(args.config)
    if args.download_dir:
        config["download_dir"] = str(args.download_dir)

    if not (config.get("vision") or {}).get("enabled", True):
        raise RuntimeError("图像识别已关闭；请先在配置中启用 vision.enabled")

    print("校准会采集按钮图片模板，不再依赖固定屏幕坐标。")
    print("请先打开一篇样例文献页面，并让 Chrome 窗口中能看到 View PDF 按钮。")
    activate_chrome(Desktop, start_if_missing=bool(config.get("safety", {}).get("start_chrome_if_missing", False)))
    input("准备好后按 Enter 开始采集 View PDF 按钮模板...")
    capture_configured_template(
        "View PDF 按钮",
        "view_pdf_template",
        pyautogui,
        config,
        args.hold_seconds,
        args.tolerance_px,
    )
    input("请打开 PDF 视图，让下载按钮可见；准备好后按 Enter 采集下载按钮模板...")
    capture_configured_template(
        "下载按钮",
        "download_template",
        pyautogui,
        config,
        args.hold_seconds,
        args.tolerance_px,
    )
    if args.save:
        input("请打开保存对话框，让保存按钮可见；准备好后按 Enter 采集保存按钮模板...")
        capture_configured_template(
            "保存按钮",
            "save_template",
            pyautogui,
            config,
            args.hold_seconds,
            args.tolerance_px,
        )
    save_config(args.config, config)
    print()
    print(f"模板校准完成，配置已保存到: {args.config}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    print(f"配置文件: {args.config}")
    config = load_config(args.config)
    download_dir = resolve_project_path(config["download_dir"])
    print(f"下载目录: {download_dir}")
    print(f"保存动作: {config['safety'].get('save_action', 'enter')}")
    if config.get("vision", {}).get("enabled", True):
        view_pdf_template = config.get("vision", {}).get("view_pdf_template")
        if view_pdf_template:
            view_pdf_template_path = resolve_template_path(str(view_pdf_template))
            print(f"View PDF 整窗模板: {'已找到' if view_pdf_template_path.exists() else '未找到'} ({view_pdf_template_path})")
        download_template = config.get("vision", {}).get("download_template")
        if download_template:
            download_template_path = resolve_template_path(str(download_template))
            print(f"下载按钮整窗模板: {'已找到' if download_template_path.exists() else '未找到'} ({download_template_path})")
        save_template = config.get("vision", {}).get("save_template")
        if save_template:
            save_template_path = resolve_template_path(str(save_template))
            print(f"保存按钮全屏模板: {'已找到' if save_template_path.exists() else '未找到'} ({save_template_path})")
        cloudflare_template = config.get("vision", {}).get("cloudflare_template")
        if cloudflare_template:
            cloudflare_template_path = resolve_template_path(str(cloudflare_template))
            print(f"Cloudflare 验证模板: {'已找到' if cloudflare_template_path.exists() else '未找到'} ({cloudflare_template_path})")
        save_action = str(config.get("safety", {}).get("save_action") or "enter")
        template_errors = required_vision_template_errors(config, save_action)
        print(f"图片识别运行条件: {'已满足' if not template_errors else '未满足'}")
        for error in template_errors:
            print(f"  - {error}")
    else:
        print("图片识别: 已关闭")

    try:
        require_gui_deps()
        print("桌面自动化依赖: 已安装")
    except RuntimeError as exc:
        print(str(exc))

    if args.ris:
        articles = parse_ris(args.ris)
        with_url = sum(1 for article in articles if article_page_url(article))
        print(f"RIS 记录数: {len(articles)}")
        print(f"可打开文章页 URL: {with_url}")
    return 0


def command_vision_test(args: argparse.Namespace) -> int:
    pyautogui, Desktop = require_gui_deps()
    config = load_config(args.config)
    vision = config.get("vision", {})
    if not vision.get("enabled", True):
        print("图像识别已关闭。")
        return 1

    chrome = activate_chrome(Desktop)
    if chrome is None:
        raise RuntimeError("未找到 Chrome 窗口，请先打开 Chrome。")

    checks = [
        ("View PDF", vision.get("view_pdf_template"), float(vision.get("match_threshold", 0.88))),
        ("下载按钮", vision.get("download_template"), float(vision.get("download_match_threshold", 0.92))),
    ]
    for name, template_value, threshold in checks:
        if not template_value:
            print(f"{name}: 未配置模板")
            continue
        template_path = resolve_template_path(str(template_value))
        if not template_path.exists():
            print(f"{name}: 模板不存在 {template_path}")
            continue
        print(f"{name}: 搜索模板 {template_path}")
        result = locate_named_template_in_chrome(
            template_path,
            Desktop,
            pyautogui,
            config,
            threshold=threshold,
        )
        if result is None:
            print(f"{name}: 没有得到匹配结果")
            continue
        x, y, score, matched = result
        status = "命中" if matched else "未达到阈值"
        print(f"{name}: {status}，位置=({x}, {y})，相似度={score:.3f}，阈值={threshold:.3f}")

    save_template = vision.get("save_template")
    if save_template:
        template_path = resolve_template_path(str(save_template))
        print(f"保存按钮: 搜索模板 {template_path}")
        result = locate_named_template_on_screen(
            template_path,
            pyautogui,
            config,
            threshold=float(vision.get("save_match_threshold", 0.9)),
        )
        if result is None:
            print("保存按钮: 没有得到匹配结果")
        else:
            x, y, score, matched = result
            status = "命中" if matched else "未达到阈值"
            print(f"保存按钮: {status}，位置=({x}, {y})，相似度={score:.3f}，阈值={float(vision.get('save_match_threshold', 0.9)):.3f}")

    cloudflare_template = vision.get("cloudflare_template")
    if cloudflare_template:
        template_path = resolve_template_path(str(cloudflare_template))
        print(f"Cloudflare: 搜索模板 {template_path}")
        result = locate_named_template_on_screen(
            template_path,
            pyautogui,
            config,
            threshold=float(vision.get("cloudflare_match_threshold", 0.82)),
        )
        if result is None:
            print("Cloudflare: 没有得到匹配结果")
        else:
            x, y, score, matched = result
            status = "命中" if matched else "未达到阈值"
            print(f"Cloudflare: {status}，位置=({x}, {y})，相似度={score:.3f}，阈值={float(vision.get('cloudflare_match_threshold', 0.82)):.3f}")
    return 0


def select_articles(
    articles: list[Article],
    state: dict[str, Any],
    start: int,
    limit: int | None,
    retry_failed: bool,
    download_dir: Path,
    filename_template: str,
    state_path: Path | None = None,
) -> list[Article]:
    selected: list[Article] = []
    items = state.get("items", {})
    for article in articles:
        if article.index < start:
            continue
        existing_pdf = find_existing_pdf(download_dir, article, filename_template)
        if existing_pdf:
            if state_path:
                update_item_state(
                    state_path,
                    state,
                    article,
                    "success",
                    file=str(existing_pdf),
                    skipped_reason="already_exists",
                )
            continue
        item_state = items.get(article.key, {})
        status = item_state.get("status")
        if status == "success":
            recorded_file = item_state.get("file")
            if recorded_file and Path(recorded_file).exists():
                continue
        selected.append(article)
        if limit is not None and len(selected) >= limit:
            break
    return selected


def command_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    timing = config["timing"]
    safety = config["safety"]

    if args.download_dir:
        config["download_dir"] = str(args.download_dir)
    if args.min_delay is not None:
        timing["min_delay_seconds"] = args.min_delay
    if args.max_delay is not None:
        timing["max_delay_seconds"] = args.max_delay
    if args.batch_limit is not None:
        timing["batch_limit"] = args.batch_limit
    if args.failure_limit is not None:
        timing["max_consecutive_failures"] = args.failure_limit
    if args.page_wait is not None:
        timing["page_wait_seconds"] = args.page_wait
    if args.view_pdf_wait is not None:
        timing["view_pdf_wait_seconds"] = args.view_pdf_wait
    if args.download_timeout is not None:
        timing["download_timeout_seconds"] = args.download_timeout

    download_dir = resolve_project_path(config["download_dir"])
    download_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report

    articles = parse_ris(args.ris)
    state = load_state(args.state)
    selected = select_articles(
        articles,
        state,
        args.start,
        args.limit,
        args.retry_failed,
        download_dir,
        config["filename_template"],
        None if args.dry_run else args.state,
    )

    if safety.get("require_user_access_notice", True):
        if not args.yes:
            print("请确认：只下载你或你的机构已经授权访问的文献；程序不会绕过登录、验证码或访问控制。")
            answer = input("确认后输入 y 继续: ").strip().lower()
            if answer != "y":
                print("已取消。")
                return 1

    print(f"待处理: {len(selected)} / RIS 总数: {len(articles)}")
    if args.dry_run:
        for article in selected:
            target_path = target_pdf_path(download_dir, article, config["filename_template"])
            print(f"[dry-run] {article.index}: {article_page_url(article)}")
            print(f"          -> {target_path}")
        write_report(report_path, articles, state, download_dir, config["filename_template"])
        return 0

    save_action = safety.get("save_action")
    if save_action is None:
        save_action = "click" if safety.get("click_save_button", False) else "enter"
    if save_action not in {"paste_path_enter", "enter", "click", "none"}:
        raise RuntimeError("配置 safety.save_action 只能是 paste_path_enter、enter、click 或 none")

    template_errors = required_vision_template_errors(config, str(save_action))
    if template_errors:
        joined = "\n".join(f"- {error}" for error in template_errors)
        raise RuntimeError(f"图片识别模板未就绪，请先运行 calibrate 或补齐模板文件:\n{joined}")

    pyautogui, Desktop = require_gui_deps()
    chrome = activate_chrome(
        Desktop,
        start_if_missing=bool(safety.get("start_chrome_if_missing", False)),
    )
    if chrome is None:
        raise RuntimeError("未找到 Chrome 窗口。请先打开 Chrome，或在配置中启用 start_chrome_if_missing。")

    consecutive_failures = 0
    processed_in_batch = 0
    queue = list(selected)
    run_attempts: dict[str, int] = {}
    max_attempts = max(1, int(safety.get("max_attempts_per_article", 2)))

    while queue:
        article = queue.pop(0)
        run_attempts[article.key] = run_attempts.get(article.key, 0) + 1
        current_attempt = run_attempts[article.key]
        page_url = article_page_url(article)
        existing_pdf = find_existing_pdf(download_dir, article, config["filename_template"])
        if existing_pdf:
            print()
            print(f"[{article.index}] 已存在，跳过: {existing_pdf}")
            update_item_state(
                args.state,
                state,
                article,
                "success",
                file=str(existing_pdf),
                skipped_reason="already_exists",
            )
            continue
        if not page_url:
            print(f"[{article.index}] 无法生成 URL，跳过: {article.title}")
            update_item_state(args.state, state, article, "failed", error="missing_url")
            consecutive_failures += 1
            continue

        print()
        print(f"[{article.index}] {article.title} (尝试 {current_attempt}/{max_attempts})")
        print(f"文章页: {page_url}")
        expected_path = target_pdf_path(download_dir, article, config["filename_template"])
        update_item_state(args.state, state, article, "running", page_url=page_url)
        before = snapshot_download_dir(download_dir)
        started_at = time.time()

        try:
            pdf_path = process_article_observe_loop(
                article,
                page_url,
                expected_path,
                download_dir,
                before,
                started_at,
                config,
                pyautogui,
                Desktop,
                save_action,
            )

            final_path = rename_pdf(
                pdf_path,
                article,
                config["filename_template"],
            )
            print(f"成功: {final_path}")
            update_item_state(
                args.state,
                state,
                article,
                "success",
                file=str(final_path),
                page_url=page_url,
            )
            close_current_tab(pyautogui, bool(safety.get("close_tab_after_article", True)))
            consecutive_failures = 0
            processed_in_batch += 1

        except KeyboardInterrupt:
            print("用户中断。")
            update_item_state(args.state, state, article, "interrupted", page_url=page_url)
            write_report(report_path, articles, state, download_dir, config["filename_template"])
            return 130
        except Exception as exc:
            consecutive_failures += 1
            print(f"失败: {exc}")
            if current_attempt < max_attempts:
                print(f"自动重试当前文献 ({current_attempt + 1}/{max_attempts})。")
                update_item_state(
                    args.state,
                    state,
                    article,
                    "retrying",
                    error=str(exc),
                    page_url=page_url,
                )
                close_current_tab(pyautogui, bool(safety.get("close_tab_after_article", True)))
                queue.insert(0, article)
                consecutive_failures = max(0, consecutive_failures - 1)
                continue

            print("达到最大尝试次数，自动跳过。")
            update_item_state(
                args.state,
                state,
                article,
                "skipped",
                error=str(exc),
                page_url=page_url,
            )
            close_current_tab(pyautogui, bool(safety.get("close_tab_after_article", True)))
            consecutive_failures = 0

        if queue and processed_in_batch >= int(timing["batch_limit"]):
            print(f"已完成本批 {processed_in_batch} 篇，自动继续下一批。")
            processed_in_batch = 0

        if queue:
            sleep_random_delay(
                int(timing["min_delay_seconds"]),
                int(timing["max_delay_seconds"]),
            )

    print("处理完成。")
    write_report(report_path, articles, state, download_dir, config["filename_template"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="用户辅助式 ScienceDirect/Elsevier PDF 下载器，不绕过登录、验证码或访问控制。",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="配置文件路径，默认 config/paper_downloader.config.json",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-config", help="生成默认配置文件")
    init_parser.add_argument("--download-dir", type=Path, help="PDF 下载目录")
    init_parser.set_defaults(func=command_init_config)

    preview_parser = subparsers.add_parser("preview", help="预览 RIS 解析结果和 PDF URL")
    preview_parser.add_argument("ris", type=Path)
    preview_parser.add_argument("--limit", type=int, default=5)
    preview_parser.set_defaults(func=command_preview)

    calibrate_parser = subparsers.add_parser("calibrate", help="采集 View PDF 和下载按钮图像模板")
    calibrate_parser.add_argument("--download-dir", type=Path, help="PDF 下载目录")
    calibrate_parser.add_argument("--hold-seconds", type=float, default=2)
    calibrate_parser.add_argument("--tolerance-px", type=int, default=3)
    calibrate_parser.add_argument("--save", action="store_true", help="同时采集保存按钮模板")
    calibrate_parser.set_defaults(func=command_calibrate)

    doctor_parser = subparsers.add_parser("doctor", help="检查配置、依赖和 RIS")
    doctor_parser.add_argument("ris", type=Path, nargs="?")
    doctor_parser.set_defaults(func=command_doctor)

    vision_parser = subparsers.add_parser("vision-test", help="测试当前 Chrome 窗口中的按钮图像识别")
    vision_parser.set_defaults(func=command_vision_test)

    run_parser = subparsers.add_parser("run", help="开始下载")
    run_parser.add_argument("ris", type=Path)
    run_parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    run_parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    run_parser.add_argument("--download-dir", type=Path)
    run_parser.add_argument("--start", type=int, default=1, help="从第几条 RIS 记录开始")
    run_parser.add_argument("--limit", type=int, help="本次最多处理几条")
    run_parser.add_argument("--retry-failed", action="store_true", help="重新处理已失败记录")
    run_parser.add_argument("--dry-run", action="store_true", help="只显示待处理 URL，不控制鼠标")
    run_parser.add_argument("--yes", action="store_true", help="跳过授权访问确认提示")
    run_parser.add_argument("--min-delay", type=int, help="每篇之间最小等待秒数")
    run_parser.add_argument("--max-delay", type=int, help="每篇之间最大等待秒数")
    run_parser.add_argument("--batch-limit", type=int, help="每批最多成功下载篇数")
    run_parser.add_argument("--failure-limit", type=int, help="连续失败几篇后暂停")
    run_parser.add_argument("--page-wait", type=int, help="打开 PDF URL 后等待秒数")
    run_parser.add_argument("--view-pdf-wait", type=int, help="点击 View PDF 后等待秒数")
    run_parser.add_argument("--download-timeout", type=int, help="等待 PDF 下载完成的超时秒数")
    run_parser.set_defaults(func=command_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    safe_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("用户中断。")
        return 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
