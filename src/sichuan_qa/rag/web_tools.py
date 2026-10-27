"""联网工具：天气（Open-Meteo）与公开票价线索（网页检索）。不是订票/余票接口。"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from sichuan_qa.logging_setup import get_logger

logger = get_logger(__name__)

USER_AGENT = "SichuanTourismQA/2.1 (tourism-assistant; +https://github.com/Gmn-bot/SichuanTourismQA)"
TIMEOUT = 8

CITY_COORDS: dict[str, tuple[float, float]] = {
    "成都": (30.67, 104.06),
    "乐山": (29.55, 103.77),
    "都江堰": (31.00, 103.65),
    "峨眉山": (29.60, 103.48),
    "宜宾": (28.76, 104.64),
    "绵阳": (31.47, 104.68),
    "德阳": (31.13, 104.40),
    "雅安": (30.01, 103.04),
    "阿坝": (31.90, 102.22),
    "甘孜": (30.05, 101.96),
    "凉山": (27.88, 102.27),
    "南充": (30.80, 106.08),
    "泸州": (28.87, 105.44),
    "自贡": (29.34, 104.78),
    "广元": (32.44, 105.84),
    "遂宁": (30.53, 105.57),
    "内江": (29.58, 105.06),
    "眉山": (30.08, 103.83),
    "广安": (30.46, 106.63),
    "达州": (31.21, 107.50),
    "巴中": (31.87, 106.75),
    "资阳": (30.13, 104.64),
    "西昌": (27.89, 102.26),
    "康定": (30.05, 101.96),
    "马尔康": (31.91, 102.22),
}

_WMO = {
    0: "晴",
    1: "多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷阵雨",
    96: "雷阵雨",
    99: "雷阵雨",
}


def http_get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def weather_label(code: Any) -> str:
    try:
        return _WMO.get(int(code), f"天气代码{code}")
    except (TypeError, ValueError):
        return "未知"


def geocode_city(name: str) -> tuple[str, float, float] | None:
    if name in CITY_COORDS:
        lat, lon = CITY_COORDS[name]
        return name, lat, lon
    q = urllib.parse.quote(name)
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=zh&format=json"
    data = http_get_json(url)
    results = data.get("results") or []
    if not results:
        return None
    row = results[0]
    return str(row.get("name") or name), float(row["latitude"]), float(row["longitude"])


def fetch_weather(city: str) -> str:
    located = geocode_city(city)
    if not located:
        return f"未能定位「{city}」，无法查询天气。"
    label, lat, lon = located
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=Asia%2FShanghai&forecast_days=2"
    )
    data = http_get_json(url)
    current = data.get("current") or {}
    daily = data.get("daily") or {}
    now = weather_label(current.get("weather_code"))
    temp = current.get("temperature_2m")
    hum = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")
    lines = [
        f"【联网天气】{label}（Open-Meteo，不是订票接口）",
        f"现在：{now}，气温 {temp}°C，湿度 {hum}%，风速 {wind} km/h",
    ]
    dates = daily.get("time") or []
    tmax = daily.get("temperature_2m_max") or []
    tmin = daily.get("temperature_2m_min") or []
    wcode = daily.get("weather_code") or []
    rain = daily.get("precipitation_probability_max") or []
    for i, day in enumerate(dates[:2]):
        bit = f"{day}：{weather_label(wcode[i] if i < len(wcode) else None)}"
        if i < len(tmin) and i < len(tmax):
            bit += f"，{tmin[i]}~{tmax[i]}°C"
        if i < len(rain) and rain[i] is not None:
            bit += f"，降水概率 {rain[i]}%"
        lines.append(bit)
    lines.append("天气仅供出行参考，以当地气象台为准。")
    return "\n".join(lines)


def search_web_snippets(query: str, limit: int = 4) -> str:
    q = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={q}"
    html = http_get_text(url)
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>', html, flags=re.I | re.S)
    if not titles:
        titles = re.findall(r'class="b_algo"[\s\S]*?<h2[^>]*>\s*<a[^>]*>(.*?)</a>', html, flags=re.I)
        snippets = re.findall(r'class="b_caption"[\s\S]*?<p>(.*?)</p>', html, flags=re.I)
    clean = re.compile(r"<[^>]+>")
    rows: list[str] = []
    for i, title in enumerate(titles[:limit]):
        title_text = clean.sub("", title)
        title_text = re.sub(r"\s+", " ", title_text).strip()
        snip = ""
        if i < len(snippets):
            snip = re.sub(r"\s+", " ", clean.sub("", snippets[i])).strip()
        if title_text:
            rows.append(f"- {title_text}" + (f"：{snip}" if snip else ""))
    if not rows:
        return "联网检索没有返回可用摘要。"
    return "【联网检索摘要】（公开网页，可能过期，以景区官网为准）\n" + "\n".join(rows)
