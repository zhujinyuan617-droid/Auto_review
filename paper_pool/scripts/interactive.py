from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from paper_downloader import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_STATE_PATH,
    find_existing_pdf,
    load_config as load_downloader_config,
    load_state,
    parse_ris,
    resolve_project_path,
    write_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_RIS_DIR = PROJECT_ROOT / "user" / "ris"
MAIN_SCRIPT = PROJECT_ROOT / "scripts" / "paper_downloader.py"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
README = PROJECT_ROOT / "README.md"
CONFIG = DEFAULT_CONFIG_PATH
STATE = DEFAULT_STATE_PATH
REPORT = DEFAULT_REPORT_PATH


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


def run_python(args: list[str]) -> int:
    command = [sys.executable, *args]
    print()
    print("即将执行:")
    print(" ".join(quote(part) for part in command))
    print()
    sys.stdout.flush()
    return subprocess.call(command, cwd=PROJECT_ROOT)


def run_downloader(args: list[str]) -> int:
    return run_python([str(MAIN_SCRIPT), *args])


def quote(value: str) -> str:
    if " " in value or "\t" in value:
        return f'"{value}"'
    return value


def choose_ris(current: Path | None = None, *, auto: bool = False) -> Path | None:
    ris_files = sorted(USER_RIS_DIR.glob("*.ris")) if USER_RIS_DIR.exists() else []
    if current and current.exists():
        print(f"当前 RIS: {current.name}")
        if auto:
            return current

    if not ris_files:
        typed = input("当前目录没有找到 .ris 文件，请输入 RIS 文件路径，留空返回: ").strip()
        return Path(typed).expanduser() if typed else current

    if len(ris_files) == 1:
        print(f"已找到 RIS: {ris_files[0].name}")
        return ris_files[0]

    if auto:
        latest = max(ris_files, key=lambda path: path.stat().st_mtime)
        print(f"检测到多个 RIS，暂用最新的: {latest.name}")
        return latest

    print("请选择 RIS 文件:")
    for index, path in enumerate(ris_files, start=1):
        print(f"  {index}. {path.name}")
    while True:
        answer = input("编号，留空返回: ").strip()
        if not answer:
            return current
        if answer.isdigit() and 1 <= int(answer) <= len(ris_files):
            return ris_files[int(answer) - 1]
        print("编号不对，再试一次。")


def ask_int(prompt: str, default: int, minimum: int | None = None) -> int:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        if not answer:
            return default
        try:
            value = int(answer)
        except ValueError:
            print("请输入数字。")
            continue
        if minimum is not None and value < minimum:
            print(f"不能小于 {minimum}。")
            continue
        return value


def ask_optional_int(prompt: str) -> int | None:
    while True:
        answer = input(f"{prompt}，留空表示不限: ").strip()
        if not answer:
            return None
        try:
            value = int(answer)
        except ValueError:
            print("请输入数字。")
            continue
        if value < 1:
            print("不能小于 1。")
            continue
        return value


def confirm(prompt: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "是", "好"}


def require_ris(ris_path: Path | None) -> Path | None:
    if ris_path and ris_path.exists():
        return ris_path
    print("还没有选择 RIS 文件。")
    return choose_ris(ris_path)


def install_deps() -> None:
    if not REQUIREMENTS.exists():
        print(f"找不到 {REQUIREMENTS}")
        return
    if confirm("现在安装/更新桌面自动化依赖吗？"):
        run_python(["-m", "pip", "install", "-r", str(REQUIREMENTS)])


def open_readme() -> None:
    if not README.exists():
        print("README.md 不存在。")
        return
    try:
        import os

        os.startfile(README)  # type: ignore[attr-defined]
    except Exception:
        print(README)


def load_config() -> dict[str, Any]:
    if not CONFIG.exists():
        run_downloader(["init-config"])
    return load_downloader_config(CONFIG)


def save_config(config: dict[str, Any]) -> None:
    CONFIG.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def configured_download_dir(config: dict[str, Any]) -> Path:
    return resolve_project_path(config.get("download_dir", "paper"))


def configure_waits() -> None:
    config = load_config()
    timing = config.setdefault("timing", {})

    print("当前等待时间:")
    print(f"  打开文章页后等待: {timing.get('page_wait_seconds', 4)} 秒")
    print(f"  点击 View PDF 后等待: {timing.get('view_pdf_wait_seconds', 4)} 秒")
    print(f"  点击下载后等待保存框: {timing.get('save_dialog_wait_seconds', 1)} 秒")
    print(f"  下载完成检测超时: {timing.get('download_timeout_seconds', 30)} 秒")
    print(f"  每篇之间随机等待: {timing.get('min_delay_seconds', 5)}-{timing.get('max_delay_seconds', 12)} 秒")
    print()

    timing["page_wait_seconds"] = ask_int(
        "打开文章页后等待秒数",
        int(timing.get("page_wait_seconds", 4)),
        minimum=0,
    )
    timing["view_pdf_wait_seconds"] = ask_int(
        "点击 View PDF 后等待秒数",
        int(timing.get("view_pdf_wait_seconds", 4)),
        minimum=0,
    )
    timing["save_dialog_wait_seconds"] = ask_int(
        "点击下载后等待保存框秒数",
        int(timing.get("save_dialog_wait_seconds", 1)),
        minimum=0,
    )
    timing["download_timeout_seconds"] = ask_int(
        "下载完成检测超时秒数",
        int(timing.get("download_timeout_seconds", 30)),
        minimum=10,
    )
    timing["min_delay_seconds"] = ask_int(
        "每篇之间最小等待秒数",
        int(timing.get("min_delay_seconds", 5)),
        minimum=0,
    )
    timing["max_delay_seconds"] = ask_int(
        "每篇之间最大等待秒数",
        int(timing.get("max_delay_seconds", 12)),
        minimum=int(timing["min_delay_seconds"]),
    )

    save_config(config)
    print(f"已保存等待时间配置: {CONFIG}")


def build_status(ris_path: Path | None) -> dict[str, Any]:
    config = load_downloader_config(CONFIG)
    download_dir = configured_download_dir(config)
    summary: dict[str, Any] = {
        "ris": ris_path,
        "download_dir": download_dir,
        "total": 0,
        "downloaded": 0,
        "pending": 0,
        "skipped_or_failed": 0,
        "other": 0,
        "state_items": 0,
    }

    if not ris_path or not ris_path.exists():
        return summary

    articles = parse_ris(ris_path)
    state = load_state(STATE) if STATE.exists() else {"items": {}}
    items = state.get("items", {})
    summary["total"] = len(articles)
    summary["state_items"] = len(items)

    for article in articles:
        existing_pdf = find_existing_pdf(
            download_dir,
            article,
            config["filename_template"],
        )
        item = items.get(article.key, {})
        status = item.get("status", "pending")
        recorded_file = item.get("file")
        recorded_exists = bool(recorded_file and Path(recorded_file).exists())
        if existing_pdf or (status == "success" and recorded_exists):
            summary["downloaded"] += 1
        elif status in {"failed", "skipped", "interrupted"}:
            summary["skipped_or_failed"] += 1
        elif status in {"running", "retrying"}:
            summary["other"] += 1
        else:
            summary["pending"] += 1

    return summary


def print_status_summary(ris_path: Path | None, *, detailed: bool = False) -> None:
    try:
        summary = build_status(ris_path)
    except Exception as exc:
        print(f"状态读取失败: {exc}")
        return

    ris_label = summary["ris"].name if summary["ris"] else "未选择"
    print(f"RIS: {ris_label}")
    print(f"保存目录: {summary['download_dir']}")
    if summary["total"]:
        print(
            "进度: "
            f"已下载 {summary['downloaded']} / "
            f"待处理 {summary['pending']} / "
            f"跳过或失败 {summary['skipped_or_failed']}"
        )
    else:
        print("进度: 暂无 RIS 记录")

    if detailed:
        print(f"状态文件: {STATE}")
        print(f"统计表: {REPORT}")
        print(f"state 记录数: {summary['state_items']}")


def refresh_report(ris_path: Path | None) -> None:
    if not ris_path or not ris_path.exists():
        print("还没有可用的 RIS 文件。")
        return
    config = load_downloader_config(CONFIG)
    download_dir = configured_download_dir(config)
    articles = parse_ris(ris_path)
    state = load_state(STATE) if STATE.exists() else {"items": {}}
    write_report(REPORT, articles, state, download_dir, config["filename_template"])


def show_main_menu(ris_path: Path | None) -> None:
    print()
    print("=" * 60)
    print("ScienceDirect/Elsevier 论文下载助手")
    print("=" * 60)
    print_status_summary(ris_path)
    print()
    print("1. 继续下载")
    print("2. 试跑 1 篇")
    print("3. 查看状态")
    print("4. 高级设置")
    print("0. 退出")


def show_advanced_menu() -> None:
    print()
    print("高级设置")
    print("-" * 60)
    print("1. 选择 RIS 文件")
    print("2. 安装/更新依赖")
    print("3. 检查环境")
    print("4. 采集 View PDF 和下载按钮模板")
    print("5. 测试按钮图像识别")
    print("6. 只预演 URL，不点击鼠标")
    print("7. 预览 RIS 和文章页 URL")
    print("8. 调整等待时间")
    print("9. 打开 README")
    print("0. 返回主菜单")


def show_run_defaults() -> None:
    config = load_config()
    timing = config.get("timing", {})
    safety = config.get("safety", {})
    print(
        "将使用当前配置: "
        f"篇间等待 {timing.get('min_delay_seconds', 5)}-"
        f"{timing.get('max_delay_seconds', 12)} 秒，"
        f"下载检测 {timing.get('download_timeout_seconds', 30)} 秒，"
        f"每篇最多尝试 {safety.get('max_attempts_per_article', 2)} 次。"
    )


def continue_download(ris_path: Path | None) -> Path | None:
    ris_path = require_ris(ris_path)
    if not ris_path:
        return ris_path

    print("继续下载会控制鼠标和键盘；遇到验证请手动完成。")
    show_run_defaults()
    limit = ask_optional_int("本次最多下载几篇")
    if not confirm("确认开始继续下载吗？"):
        return ris_path

    args = ["run", str(ris_path), "--yes"]
    if limit is not None:
        args.extend(["--limit", str(limit)])
    run_downloader(args)
    return ris_path


def trial_run(ris_path: Path | None) -> Path | None:
    ris_path = require_ris(ris_path)
    if not ris_path:
        return ris_path

    print("试跑会控制鼠标和键盘，只处理下一篇待处理文献。")
    if confirm("确认试跑 1 篇吗？"):
        run_downloader(["run", str(ris_path), "--limit", "1", "--yes"])
    return ris_path


def preview_urls(ris_path: Path | None) -> Path | None:
    ris_path = require_ris(ris_path)
    if not ris_path:
        return ris_path
    limit = ask_int("预演几条", 3, minimum=1)
    run_downloader(["run", str(ris_path), "--limit", str(limit), "--dry-run", "--yes"])
    return ris_path


def preview_ris(ris_path: Path | None) -> Path | None:
    ris_path = require_ris(ris_path)
    if not ris_path:
        return ris_path
    limit = ask_int("预览几条", 5, minimum=1)
    run_downloader(["preview", str(ris_path), "--limit", str(limit)])
    return ris_path


def advanced_menu(ris_path: Path | None) -> Path | None:
    while True:
        show_advanced_menu()
        choice = input("请选择: ").strip()

        if choice == "0":
            return ris_path

        if choice == "1":
            ris_path = choose_ris(ris_path)

        elif choice == "2":
            install_deps()

        elif choice == "3":
            ris_path = require_ris(ris_path)
            args = ["doctor"]
            if ris_path:
                args.append(str(ris_path))
            run_downloader(args)

        elif choice == "4":
            print("请先手动打开一篇样例文献页面。")
            print("之后按提示把鼠标停在 View PDF 和下载按钮上，用于采集图片模板。保存对话框默认用 Enter。")
            input("准备好后按 Enter 开始采集模板...")
            run_downloader(["calibrate"])

        elif choice == "5":
            print("请先把 Chrome 停在包含 View PDF、下载按钮、保存框或验证提示的页面。")
            run_downloader(["vision-test"])

        elif choice == "6":
            ris_path = preview_urls(ris_path)

        elif choice == "7":
            ris_path = preview_ris(ris_path)

        elif choice == "8":
            configure_waits()

        elif choice == "9":
            open_readme()

        else:
            print("没有这个选项。")
            input("按 Enter 返回高级菜单...")
            continue

        input("按 Enter 返回高级菜单...")


def main() -> int:
    safe_console()
    if not MAIN_SCRIPT.exists():
        print(f"找不到主脚本: {MAIN_SCRIPT}")
        return 1

    ris_path = choose_ris(auto=True)
    while True:
        show_main_menu(ris_path)
        choice = input("请选择: ").strip()

        if choice == "0":
            print("已退出。")
            return 0

        if choice == "1":
            ris_path = continue_download(ris_path)

        elif choice == "2":
            ris_path = trial_run(ris_path)

        elif choice == "3":
            print_status_summary(ris_path, detailed=True)
            refresh_report(ris_path)

        elif choice == "4":
            ris_path = advanced_menu(ris_path)

        else:
            print("没有这个选项。")
            input("按 Enter 返回菜单...")
            continue

        input("按 Enter 返回菜单...")


if __name__ == "__main__":
    raise SystemExit(main())
