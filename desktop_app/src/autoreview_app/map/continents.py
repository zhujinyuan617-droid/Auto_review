"""国别(ISO-3166 alpha-2)→ 洲 的静态映射(Wave-3 ④ 机构五大洲镜头)。

OpenAlex 的机构对象只给 country_code,不给洲;洲在本地映射。
键与显示名集中在这里,镜头与测试共用;查不到的国家归 None(前端落"机构信息缺失"区)。
"""
from __future__ import annotations

CONTINENT_LABELS = {
    "asia": "亚洲",
    "europe": "欧洲",
    "north-america": "北美洲",
    "south-america": "南美洲",
    "africa": "非洲",
    "oceania": "大洋洲",
}

_C = {
    "asia": [
        "CN", "HK", "MO", "TW", "JP", "KR", "KP", "MN", "IN", "PK", "BD", "LK", "NP", "BT",
        "MV", "AF", "IR", "IQ", "SY", "LB", "JO", "IL", "PS", "SA", "AE", "QA", "KW", "BH",
        "OM", "YE", "TR", "GE", "AM", "AZ", "KZ", "UZ", "TM", "KG", "TJ", "TH", "VN", "LA",
        "KH", "MM", "MY", "SG", "ID", "BN", "PH", "TL", "CY",
    ],
    "europe": [
        "GB", "IE", "FR", "DE", "NL", "BE", "LU", "CH", "AT", "IT", "ES", "PT", "GR", "MT",
        "NO", "SE", "FI", "DK", "IS", "PL", "CZ", "SK", "HU", "RO", "BG", "HR", "SI", "RS",
        "BA", "ME", "MK", "AL", "EE", "LV", "LT", "BY", "UA", "MD", "RU", "AD", "MC", "SM",
        "VA", "LI", "XK",
    ],
    "north-america": [
        "US", "CA", "MX", "GT", "BZ", "SV", "HN", "NI", "CR", "PA", "CU", "DO", "HT", "JM",
        "TT", "BS", "BB", "PR", "GL",
    ],
    "south-america": [
        "BR", "AR", "CL", "CO", "PE", "VE", "EC", "BO", "PY", "UY", "GY", "SR", "GF",
    ],
    "africa": [
        "ZA", "EG", "NG", "DZ", "MA", "TN", "LY", "ET", "KE", "TZ", "UG", "GH", "CI", "SN",
        "CM", "ZW", "ZM", "MZ", "AO", "NA", "BW", "RW", "SD", "SS", "CD", "CG", "GA", "ML",
        "BF", "NE", "TD", "MR", "MG", "MW", "BJ", "TG", "GN", "SL", "LR", "GM", "MU", "SC",
    ],
    "oceania": ["AU", "NZ", "PG", "FJ", "SB", "VU", "WS", "TO", "NC", "PF"],
}

COUNTRY_TO_CONTINENT: dict[str, str] = {
    cc: cont for cont, codes in _C.items() for cc in codes
}


def continent_of(country_code: str | None) -> str | None:
    """ISO-2 国别码 → 洲键;未知/缺失 → None。大小写不敏感。"""
    if not country_code:
        return None
    return COUNTRY_TO_CONTINENT.get(str(country_code).strip().upper())
