from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RegexPreset:
    key: str
    label: str
    pattern: str
    description: str


REGEX_PRESETS = {
    "china_mobile": RegexPreset(
        key="china_mobile",
        label="中国大陆手机号",
        pattern=r"(?<!\d)1(?:3[0-9]|4[01456879]|5[0-35-9]|6[2567]|7[0-8]|8[0-9]|9[0-35-9])\d{8}(?!\d)",
        description="匹配中国大陆 11 位手机号码；只有同一个号码出现在 2 个及以上分组时才预警。",
    ),
    "china_id_card": RegexPreset(
        key="china_id_card",
        label="中国大陆身份证",
        pattern=r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)",
        description="匹配常见 18 位中国居民身份证号码格式；只有同一个号码跨组出现时才预警。",
    ),
    "email": RegexPreset(
        key="email",
        label="邮箱地址",
        pattern=(
            r"(?<![A-Za-z0-9_.+-])(?![A-Za-z0-9_.+-]*\.\.)"
            r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![A-Za-z0-9_.+-])"
        ),
        description="匹配常见邮箱地址；只有同一个邮箱地址出现在 2 个及以上分组时才预警。",
    ),
    "china_address": RegexPreset(
        key="china_address",
        label="地址",
        pattern=(
            r"(?:北京市|上海市|天津市|重庆市|[一-龥]+省)(?:[一-龥]+市)?"
            r"(?:[一-龥]+(?:区|县))(?:[一-龥]+(?:街道|路|巷|镇|乡))"
            r"(?:[一-龥0-9]+号)(?:[一-龥0-9]+单元)?(?:[一-龥0-9]+室)?"
        ),
        description="匹配包含省市区县、道路或乡镇及门牌号的常见中文地址；只有同一个地址跨组出现时才预警。",
    ),
}


def default_regex_presets() -> dict[str, bool]:
    return {key: True for key in REGEX_PRESETS}


def normalize_regex_presets(raw: Any) -> dict[str, bool]:
    defaults = default_regex_presets()
    if raw is None:
        return defaults
    if not isinstance(raw, dict):
        raise ValueError("regex_presets 必须是对象，例如 {\"china_mobile\": true}。")
    return {key: _coerce_bool(raw.get(key, enabled)) for key, enabled in defaults.items()}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "是"}
    return bool(value)
