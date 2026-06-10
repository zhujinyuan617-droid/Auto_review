"""Wave-3 ④:洲映射 + 国别补查脚本(enrich_registry 注入假 lookup,零网络)。"""
import importlib.util
from pathlib import Path

from autoreview_app.map.continents import CONTINENT_LABELS, continent_of


def _load_script():
    p = Path(__file__).resolve().parents[1] / "scripts" / "enrich_institution_countries.py"
    spec = importlib.util.spec_from_file_location("enrich_institution_countries", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_continent_of_basics():
    assert continent_of("CN") == "asia"
    assert continent_of("us") == "north-america"  # 大小写不敏感
    assert continent_of("DE") == "europe"
    assert continent_of("BR") == "south-america"
    assert continent_of("ZA") == "africa"
    assert continent_of("AU") == "oceania"
    assert continent_of(None) is None
    assert continent_of("") is None
    assert continent_of("XX") is None  # 未收录国别 → None(落"机构信息缺失"区)
    assert set(CONTINENT_LABELS) == {"asia", "europe", "north-america",
                                     "south-america", "africa", "oceania"}


def _registry(entries):
    return {"schema_version": "0.1.0", "facets": ["institution"], "entries": entries}


def test_enrich_registry_fills_missing_only():
    mod = _load_script()
    reg = _registry({
        "elem:institution/a": {"id": "elem:institution/a", "display_name": "Alpha U",
                               "aliases": [], "redirect_to": None},
        "elem:institution/b": {"id": "elem:institution/b", "display_name": "Beta U",
                               "aliases": [], "redirect_to": None, "country_code": "US"},
        "elem:institution/c": {"id": "elem:institution/c", "display_name": "Gone U",
                               "aliases": [], "redirect_to": "elem:institution/a"},
        "elem:institution/d": {"id": "elem:institution/d", "display_name": "NoHit U",
                               "aliases": [], "redirect_to": None},
    })
    calls = []

    def fake_lookup(name):
        calls.append(name)
        if name == "Alpha U":
            return {"id": "https://openalex.org/I1", "display_name": "Alpha University",
                    "country_code": "cn"}
        return None

    stats = mod.enrich_registry(reg, fake_lookup)
    # redirect 条目不参与;已有国别的跳过;无命中的留空
    assert calls == ["Alpha U", "NoHit U"]
    assert stats == {"total": 3, "skipped": 1, "matched": 1, "no_hit": 1, "no_country": 0}
    a = reg["entries"]["elem:institution/a"]
    assert a["country_code"] == "CN"  # 大写归一
    assert a["openalex_id"] == "https://openalex.org/I1"
    assert a["openalex_match_name"] == "Alpha University"  # 错配留底供核对
    assert a["country_source"] == "openalex-search"
    assert "country_code" not in reg["entries"]["elem:institution/d"]


def test_enrich_registry_force_requeries():
    mod = _load_script()
    reg = _registry({
        "elem:institution/b": {"id": "elem:institution/b", "display_name": "Beta U",
                               "aliases": [], "redirect_to": None, "country_code": "US"},
    })
    stats = mod.enrich_registry(
        reg, lambda n: {"id": "I2", "display_name": "Beta University", "country_code": "GB"},
        force=True)
    assert stats["matched"] == 1 and stats["skipped"] == 0
    assert reg["entries"]["elem:institution/b"]["country_code"] == "GB"
