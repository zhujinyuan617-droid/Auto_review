"""i18n 词典守卫:键集一致、占位符一致、行格式合法(逮未转义引号类错误)。"""
import re
from pathlib import Path

I18N_DIR = Path(__file__).resolve().parents[1] / "frontend" / "i18n"
# 一对 "key": "value"(键和值都允许 \" 转义)
PAIR = re.compile(r'"((?:[^"\\]|\\.)+)"\s*:\s*"((?:[^"\\]|\\.)*)"')
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _load(name: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw in (I18N_DIR / name).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if (not line or line.startswith("//") or line.startswith("export const")
                or line in ("};", "}")):
            continue
        found = list(PAIR.finditer(line))
        # 剥掉已匹配的对子和分隔符后,只许剩空白或行尾注释;有残渣=畸形行(如未转义引号)
        residue = PAIR.sub("", line)
        residue = re.sub(r"//.*$", "", residue)
        residue = residue.replace(",", "").replace(":", "").strip()
        assert found and residue == "", f"{name} 畸形词典行: {line}"
        for m in found:
            key = m.group(1)
            assert key not in pairs, f"{name} 重复键: {key}"
            pairs[key] = m.group(2)
    assert pairs, f"{name} 没解析出任何键"
    return pairs


def test_key_sets_identical():
    zh, en = _load("zh.js"), _load("en.js")
    only_zh = sorted(set(zh) - set(en))
    only_en = sorted(set(en) - set(zh))
    assert not only_zh and not only_en, f"键集不一致 only_zh={only_zh} only_en={only_en}"


def test_placeholder_parity():
    zh, en = _load("zh.js"), _load("en.js")
    bad = [k for k in zh if set(PLACEHOLDER.findall(zh[k])) != set(PLACEHOLDER.findall(en[k]))]
    assert not bad, f"占位符不一致的键: {bad}"


def test_dicts_parse_clean():
    # _load 内部的畸形行断言即格式闸;两本都能完整解析就算过
    assert len(_load("zh.js")) == len(_load("en.js"))
