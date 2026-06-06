from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from getpass import getpass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import AIClientError, OpenAICompatibleClient, load_ai_config


CONFIG_PATH = ROOT / "config" / "ai.local.json"
HANDOFF = ROOT / "HANDOFF.md"
CONNECTION_PLAN = ROOT / "CONNECTION_PLAN.md"
ISSUES = ROOT / "ISSUES.md"
GRAPH_HTML = ROOT / "reports" / "connection" / "graph.html"
STAGES = ["clean", "sections", "reading", "card", "evidence_atoms", "paper_syntheses", "validate"]
AI_CONFIG_ARG = "config\\ai.local.json"


PRESETS = {
    "1": {
        "label": "DeepSeek 推荐，便宜",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    "2": {
        "label": "OpenAI 官方接口",
        "base_url": "https://api.openai.com/v1",
        "model": "",
    },
    "3": {
        "label": "其他 OpenAI-compatible 接口，自定义 URL",
        "base_url": "",
        "model": "",
    },
}


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


def quote(value: str) -> str:
    if " " in value or "\t" in value:
        return f'"{value}"'
    return value


def command_text(command: list[str]) -> str:
    return " ".join(quote(part) for part in command)


def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_command(command: list[str], *, cwd: Path = ROOT) -> int:
    print()
    print("即将执行:")
    print(command_text(command))
    print()
    sys.stdout.flush()
    return subprocess.call(command, cwd=cwd, env=child_env())


def capture_command(command: list[str], *, cwd: Path = ROOT) -> tuple[int, str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=child_env(),
    )
    output = completed.stdout or ""
    if completed.stderr:
        output += "\n[stderr]\n" + completed.stderr
    return completed.returncode, output.strip()


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None and default != "" else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    if not answer and default is not None:
        return default
    return answer


def ask_secret(prompt: str) -> str:
    try:
        return getpass(f"{prompt}: ").strip()
    except Exception:
        print("当前终端不支持隐藏输入，将使用普通输入。")
        return ask(prompt)


def confirm(prompt: str, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes", "是", "好", "1"}


def pause() -> None:
    input("\n按 Enter 返回菜单...")


def open_file(path: Path) -> None:
    if not path.exists():
        print(f"找不到文件: {path}")
        return
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        print(path)


def read_local_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_local_config(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def redacted_config_summary() -> None:
    print()
    print("AI 配置状态:")
    print(f"  配置文件: {CONFIG_PATH}")
    print(f"  文件存在: {'是' if CONFIG_PATH.exists() else '否'}")
    try:
        config = load_ai_config(ROOT)
    except AIClientError as exc:
        print(f"  状态: 不可用")
        print(f"  原因: {exc}")
        return
    print("  状态: 可用")
    print(f"  provider: {config.provider}")
    print(f"  base_url: {config.base_url}")
    print("  api_key: 已设置，不显示")
    print(f"  model: {config.model}")
    print(f"  timeout_seconds: {config.timeout_seconds}")
    print(f"  max_retries: {config.max_retries}")
    print(f"  temperature: {config.temperature}")


def configure_ai() -> bool:
    print()
    print("AI 配置向导")
    print("这个文件只保存在本机，已被 Git 忽略，不会上传。")
    print()
    for key, preset in PRESETS.items():
        print(f"{key}. {preset['label']}")
    print("0. 返回")

    choice = ask("请选择接口类型")
    if choice == "0":
        return False
    preset = PRESETS.get(choice)
    if not preset:
        print("选择无效。")
        return False

    base_url = preset["base_url"]
    if not base_url:
        base_url = ask("请输入 OpenAI-compatible base_url，例如 https://api.example.com/v1")
    else:
        print(f"base_url: {base_url}")
        if choice != "1" and not confirm("是否使用这个 base_url？", True):
            base_url = ask("请输入 base_url", base_url)

    api_key = ask_secret("请输入 API Key")
    if not api_key:
        print("API Key 不能为空。")
        return False

    model_default = preset["model"]
    model = ask("请输入模型名", model_default)
    if not model:
        print("模型名不能为空。")
        return False

    timeout_text = ask("请求超时秒数", "120")
    retries_text = ask("最大重试次数", "3")
    temperature_text = ask("temperature", "0.1")
    try:
        timeout_seconds = int(timeout_text)
        max_retries = int(retries_text)
        temperature = float(temperature_text)
    except ValueError:
        print("timeout/max_retries/temperature 格式不正确。")
        return False

    data = {
        "provider": "openai_compatible",
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "max_retries": max_retries,
        "temperature": temperature,
    }
    write_local_config(data)
    print()
    print("已保存 AI 配置。")
    redacted_config_summary()
    if confirm("现在测试 AI 连接吗？", True):
        return test_ai_connection()
    return True


def test_ai_connection() -> bool:
    print()
    print("正在测试 AI 连接...")
    try:
        config = load_ai_config(ROOT)
        client = OpenAICompatibleClient(config)
        result = client.chat_json(
            [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": 'Return exactly {"status":"ok"} as JSON.'},
            ],
            "Return only a JSON object with key status.",
        )
    except AIClientError as exc:
        print(f"AI 连接失败: {exc}")
        return False
    status = str(result.get("status") or "").lower()
    if status == "ok":
        print("AI 连接成功。")
        return True
    print(f"AI 有响应，但返回内容不符合预期: {result}")
    return False


def ensure_ai_ready() -> bool:
    try:
        load_ai_config(ROOT)
        return True
    except AIClientError as exc:
        print()
        print(f"AI 目前不可用: {exc}")
        if confirm("是否现在进入 AI 配置向导？", True):
            return configure_ai()
        return False


def local_status() -> dict[str, Any]:
    status: dict[str, Any] = {}
    code, git_output = capture_command(["git", "status", "--short"], cwd=REPO_ROOT)
    status["git_status_code"] = code
    status["git_status"] = git_output or "(clean)"
    status["ai_config_exists"] = CONFIG_PATH.exists()
    try:
        config = load_ai_config(ROOT)
        status["ai_status"] = "ok"
        status["ai_base_url"] = config.base_url
        status["ai_model"] = config.model
    except AIClientError as exc:
        status["ai_status"] = "error"
        status["ai_error"] = str(exc)

    docling_path = ROOT / "envs" / "docling" / "Scripts" / "docling.exe"
    status["docling_runtime_exists"] = docling_path.exists()
    status["s05_library_exists"] = (ROOT / "library" / "S05").exists()
    for filename in [
        "content_blocks.json",
        "ai_sections.json",
        "reading_blocks.json",
        "literature_card.json",
        "evidence_atoms.json",
        "paper_syntheses.json",
    ]:
        status[f"s05_{filename}"] = (ROOT / "library" / "S05" / filename).exists()
    return status


def print_local_status() -> None:
    status = local_status()
    print()
    print("本地状态检查")
    print(f"  Git 状态: {status['git_status']}")
    print(f"  AI 配置: {status.get('ai_status')}")
    if status.get("ai_status") == "ok":
        print(f"  AI base_url: {status.get('ai_base_url')}")
        print(f"  AI model: {status.get('ai_model')}")
    else:
        print(f"  AI 问题: {status.get('ai_error')}")
    print(f"  Docling runtime: {'存在' if status['docling_runtime_exists'] else '缺失'}")
    print(f"  S05 library: {'存在' if status['s05_library_exists'] else '缺失'}")
    for key, value in status.items():
        if key.startswith("s05_") and key.endswith(".json"):
            print(f"  {key[4:]}: {'存在' if value else '缺失'}")


def validate_s05() -> int:
    return run_command(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_pipeline.py"),
            "--paper-id",
            "S05",
            "--stage",
            "validate",
            "--library-dir",
            "library",
            "--reports-dir",
            "reports",
        ]
    )


def dry_run_paper() -> int:
    paper_id = ask("请输入 paper_id", "S05").upper()
    return run_command(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_from_paper_downloads.py"),
            "--paper-id",
            paper_id,
            "--skip-ingest",
            "--skip-docling",
            "--dry-run",
        ]
    )


def run_stage() -> int:
    paper_id = ask("请输入 paper_id", "S05").upper()
    print("可选 stage:")
    for index, stage in enumerate(STAGES, start=1):
        print(f"  {index}. {stage}")
    choice = ask("请选择 stage 编号", "7")
    if not choice.isdigit() or not 1 <= int(choice) <= len(STAGES):
        print("stage 选择无效。")
        return 2
    stage = STAGES[int(choice) - 1]
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_pipeline.py"),
        "--paper-id",
        paper_id,
        "--stage",
        stage,
        "--library-dir",
        "library",
        "--reports-dir",
        "reports",
    ]
    if stage == "clean":
        command.extend(
            [
                "--json-dir",
                "data\\docling\\json",
                "--md-dir",
                "data\\docling\\md",
                "--pdf-dir",
                "data\\ingest\\pdfs",
                "--pdf-dir",
                "..\\paper_pool\\paper",
            ]
        )
    if stage != "validate" and confirm("是否强制刷新 AI/阶段输出？", False):
        command.append("--force")
    print()
    if not confirm(f"确认运行 {paper_id} 的 {stage} 阶段？", False):
        print("已取消。")
        return 0
    return run_command(command)


def full_library_dry_run() -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_from_paper_downloads.py"),
        "--all",
        "--config",
        AI_CONFIG_ARG,
        "--parallel",
        ask("pipeline 并行数", "6"),
        "--docling-parallel",
        ask("Docling 并行数", "2"),
        "--resume",
        "--dry-run",
    ]
    print()
    print("这一步只打印计划，不会真正跑 Docling 或 AI。")
    if not confirm("确认做全库扩容 dry-run？", True):
        print("已取消。")
        return 0
    return run_command(command)


def run_full_library() -> int:
    if not ensure_ai_ready():
        return 1
    parallel = ask("pipeline 并行数", "6")
    docling_parallel = ask("Docling 并行数", "2")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_from_paper_downloads.py"),
        "--all",
        "--config",
        AI_CONFIG_ARG,
        "--parallel",
        parallel,
        "--docling-parallel",
        docling_parallel,
        "--resume",
    ]
    print()
    print("这一步会处理 manifest 里的 active 英文论文。")
    print("中文/非英文/非文章默认跳过；不要加 --include-deferred。")
    print("可能耗时较久，并会消耗 AI token。")
    if not confirm("确认正式运行全库扩容？", False):
        print("已取消。")
        return 0
    return run_command(command)


def run_full_library_with_recovery() -> int:
    if not ensure_ai_ready():
        return 1
    parallel = ask("pipeline 并行数", "6")
    docling_parallel = ask("Docling 并行数", "2")
    recovery_passes = ask("自动恢复轮数", "1")
    retry_docling = confirm("Docling 失败是否低并发重试一次？默认只标记坏 PDF", False)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_workflow_with_recovery.py"),
        "--all",
        "--config",
        AI_CONFIG_ARG,
        "--parallel",
        parallel,
        "--docling-parallel",
        docling_parallel,
        "--max-recovery-passes",
        recovery_passes,
    ]
    if retry_docling:
        command.append("--retry-docling-once")
    print()
    print("这一步会执行主流程，并把失败项写入 recovery_queue.json。")
    print("Docling 失败默认只标记并排除；AI/validator 阶段失败会按失败阶段强制重跑一次。")
    print("它不会手工修改 AI 生成内容，也不会处理 deferred 中文/非文章记录。")
    if not confirm("确认启动带恢复的全库运行？", False):
        print("已取消。")
        return 0
    return run_command(command)


def rebuild_connection_layer() -> int:
    if not ensure_ai_ready():
        return 1
    workers = ask("AI 判关系并行数", "6")
    source_mode = "on" if confirm("判关系时额外喂 abstract/conclusion？更慢但更稳", False) else "off"
    force_edges = confirm("是否强制重判关系并忽略 edge cache？", False)
    steps = [
        [
            sys.executable,
            str(ROOT / "scripts" / "connect" / "build_vocabulary.py"),
            "--library-dir",
            "library",
            "--config",
            AI_CONFIG_ARG,
        ],
        [
            sys.executable,
            str(ROOT / "scripts" / "connect" / "build_candidate_edges.py"),
            "--library-dir",
            "library",
        ],
        [
            sys.executable,
            str(ROOT / "scripts" / "connect" / "ai_build_edges.py"),
            "--config",
            AI_CONFIG_ARG,
            "--workers",
            workers,
            "--source",
            source_mode,
        ],
        [
            sys.executable,
            str(ROOT / "scripts" / "connect" / "build_concept_index.py"),
            "--library-dir",
            "library",
        ],
        [
            sys.executable,
            str(ROOT / "scripts" / "use" / "build_graph_html.py"),
        ],
    ]
    if force_edges:
        steps[2].append("--force")
    print()
    print("将按顺序重建: 词表 -> 候选边 -> AI typed edges -> 概念索引 -> HTML 图谱。")
    print("注意: 重建后 angles 和旧草稿都应视为可再生旧产物。")
    for index, command in enumerate(steps, start=1):
        print(f"  {index}. {command_text(command)}")
    if not confirm("确认重建连接层？", False):
        print("已取消。")
        return 0
    for command in steps:
        code = run_command(command)
        if code != 0:
            print(f"步骤失败，退出码: {code}")
            return code
    return 0


def build_graph() -> int:
    code = run_command([sys.executable, str(ROOT / "scripts" / "use" / "build_graph_html.py")])
    if code == 0 and GRAPH_HTML.exists() and confirm("是否现在打开图谱？", True):
        open_file(GRAPH_HTML)
    return code


def propose_angles() -> int:
    if not ensure_ai_ready():
        return 1
    n = ask("希望生成几个候选角度", "6")
    model = ask("模型名", "deepseek-v4-pro")
    print()
    print("这一步只生成候选角度，不证明角度为真。重要角度还要用复核菜单验证。")
    if not confirm("确认让 AI 提出候选综述角度？", True):
        print("已取消。")
        return 0
    return run_command(
        [
            sys.executable,
            str(ROOT / "scripts" / "use" / "propose_angles.py"),
            "--config",
            AI_CONFIG_ARG,
            "--n",
            n,
            "--model",
            model,
        ]
    )


def query_network() -> int:
    print()
    print("1. 按概念查询")
    print("2. 按论文查询")
    choice = ask("请选择", "1")
    if choice == "1":
        concept = ask("请输入概念，例如 capillary condensation")
        if not concept:
            print("概念不能为空。")
            return 2
        return run_command([sys.executable, str(ROOT / "scripts" / "use" / "query_network.py"), "--concept", concept])
    if choice == "2":
        paper_id = ask("请输入 paper_id", "S18").upper()
        return run_command([sys.executable, str(ROOT / "scripts" / "use" / "query_network.py"), "--paper", paper_id])
    print("选择无效。")
    return 2


def verify_angle() -> int:
    if not ensure_ai_ready():
        return 1
    papers = ask("请输入论文 id，用逗号分隔，例如 S121,S43")
    claim = ask("请输入要复核的关系/论点")
    if not papers or not claim:
        print("论文 id 和论点都不能为空。")
        return 2
    model = ask("验证模型", "deepseek-v4-pro")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "use" / "verify_angle.py"),
        "--papers",
        papers,
        "--claim",
        claim,
        "--model",
        model,
        "--config",
        AI_CONFIG_ARG,
    ]
    print()
    print("这一步会喂全文给 AI 做对抗式复核，通常比普通调用更慢、更贵。")
    if not confirm("确认复核这个角度？", True):
        print("已取消。")
        return 0
    return run_command(command)


def draft_section() -> int:
    if not ensure_ai_ready():
        return 1
    concept = ask("请输入出稿概念，例如 capillary condensation")
    if not concept:
        print("概念不能为空。")
        return 2
    command = [
        sys.executable,
        str(ROOT / "scripts" / "use" / "draft_section.py"),
        "--concept",
        concept,
        "--config",
        AI_CONFIG_ARG,
    ]
    if confirm("是否加入风格语料文件/目录？", False):
        corpus = ask("请输入风格语料路径")
        if corpus:
            command.extend(["--style-corpus", corpus])
    print()
    print("出稿只使用关联网和原文片段；生成后仍要人工读证据。")
    if not confirm("确认按这个概念出稿？", True):
        print("已取消。")
        return 0
    return run_command(command)


def latest_logs(max_files: int = 8) -> list[Path]:
    reports = ROOT / "reports"
    if not reports.exists():
        return []
    logs = sorted(reports.glob("pipeline_*/logs/*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    logs.extend(sorted(reports.glob("from_downloads_*/logs/*.log"), key=lambda path: path.stat().st_mtime, reverse=True))
    return logs[:max_files]


def diagnose_with_ai() -> bool:
    if not ensure_ai_ready():
        return False
    logs = latest_logs()
    if not logs:
        print("没有找到可诊断的日志。")
        return False
    payload = []
    for path in logs:
        text = path.read_text(encoding="utf-8", errors="replace")
        payload.append(
            {
                "path": str(path.relative_to(ROOT)),
                "tail": text[-3000:],
            }
        )
    prompt = {
        "task": "Diagnose the recent Auto Review pipeline logs for a non-programmer user.",
        "rules": [
            "Answer in Chinese.",
            "Do not ask the user to edit generated JSON by hand.",
            "Prefer safe dry-run or validation commands.",
            "Mention whether AI config, Docling, validation, or fallback seems involved.",
        ],
        "logs": payload,
    }
    try:
        client = OpenAICompatibleClient(load_ai_config(ROOT))
        result = client.chat_json(
            [
                {"role": "system", "content": "You are an Auto Review operations assistant. Return strict JSON."},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            "Return JSON with keys summary, likely_issue, recommended_next_steps.",
        )
    except AIClientError as exc:
        print(f"AI 诊断失败: {exc}")
        return False
    print()
    print("AI 诊断结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return True


def next_step_with_ai() -> bool:
    if not ensure_ai_ready():
        return False
    status = local_status()
    try:
        client = OpenAICompatibleClient(load_ai_config(ROOT))
        result = client.chat_json(
            [
                {"role": "system", "content": "You are an Auto Review operations assistant. Return strict JSON."},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Suggest the safest next step for a non-programmer user.",
                            "status": status,
                            "available_actions": [
                                "configure_ai",
                                "test_ai",
                                "validate_s05",
                                "dry_run_paper",
                                "run_one_stage",
                                "full_library_dry_run",
                                "run_full_library",
                                "rebuild_connection_layer",
                                "build_graph",
                                "propose_angles",
                                "query_network",
                                "verify_angle",
                                "draft_section",
                                "read_handoff",
                            ],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "Return JSON with keys summary, next_step, command, caution.",
        )
    except AIClientError as exc:
        print(f"AI 建议失败: {exc}")
        return False
    print()
    print("AI 下一步建议:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return True


def print_menu() -> None:
    print()
    print("=" * 60)
    print("Auto Review Assistant")
    print("=" * 60)
    print("基础:")
    print("  1. 一键检查当前状态")
    print("  2. 配置或重配 AI")
    print("  3. 测试 AI 连接")
    print("  4. 验证 S05 smoke test")
    print("  5. 对某篇论文做 dry-run")
    print("  6. 运行某篇论文的指定阶段")
    print()
    print("v2 主线:")
    print("  10. 全库扩容 dry-run")
    print("  11. 正式全库扩容")
    print("  12. 带恢复的智能全库运行")
    print("  13. 重建连接层")
    print("  14. 生成/打开图谱")
    print("  15. AI 提出候选综述角度")
    print("  16. 查询关联网")
    print("  17. 复核某个角度")
    print("  18. 按概念接地出稿")
    print()
    print("辅助:")
    print("  20. AI 诊断最近日志")
    print("  21. AI 给下一步建议")
    print("  22. 打开 HANDOFF.md")
    print("  23. 打开 CONNECTION_PLAN.md")
    print("  24. 打开 ISSUES.md")
    print("0. 退出")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive Auto Review assistant.")
    parser.add_argument("--status", action="store_true", help="Print local status once and exit.")
    parser.add_argument("--test-ai", action="store_true", help="Test AI connection once and exit.")
    parser.add_argument("--validate-s05", action="store_true", help="Run the S05 validation smoke test once and exit.")
    return parser.parse_args()


def main() -> int:
    safe_console()
    args = parse_args()
    if args.status:
        print_local_status()
        return 0
    if args.test_ai:
        return 0 if test_ai_connection() else 1
    if args.validate_s05:
        return validate_s05()

    print("Auto Review Assistant 启动中...")
    if not CONFIG_PATH.exists():
        print("未找到 AI 配置。你仍然可以使用本地检查功能。")
        if confirm("是否现在配置 AI？", True):
            configure_ai()

    while True:
        print_menu()
        choice = ask("请选择")
        if choice == "0":
            return 0
        if choice == "1":
            print_local_status()
            pause()
        elif choice == "2":
            configure_ai()
            pause()
        elif choice == "3":
            test_ai_connection()
            pause()
        elif choice == "4":
            validate_s05()
            pause()
        elif choice == "5":
            dry_run_paper()
            pause()
        elif choice == "6":
            run_stage()
            pause()
        elif choice == "10":
            full_library_dry_run()
            pause()
        elif choice == "11":
            run_full_library()
            pause()
        elif choice == "12":
            run_full_library_with_recovery()
            pause()
        elif choice == "13":
            rebuild_connection_layer()
            pause()
        elif choice == "14":
            build_graph()
            pause()
        elif choice == "15":
            propose_angles()
            pause()
        elif choice == "16":
            query_network()
            pause()
        elif choice == "17":
            verify_angle()
            pause()
        elif choice == "18":
            draft_section()
            pause()
        elif choice == "20":
            diagnose_with_ai()
            pause()
        elif choice == "21":
            next_step_with_ai()
            pause()
        elif choice == "22":
            open_file(HANDOFF)
            pause()
        elif choice == "23":
            open_file(CONNECTION_PLAN)
            pause()
        elif choice == "24":
            open_file(ISSUES)
            pause()
        else:
            print("选择无效。")
            pause()


if __name__ == "__main__":
    raise SystemExit(main())
