#!/usr/bin/env python3
"""
JRE Policy Bank — daily refresh from public info.gov.hk press releases.

Usage:
  python3 scripts/refresh_policies.py
  python3 scripts/refresh_policies.py --days 7 --max-new 10

Prefer Traditional Chinese day indexes (*c.htm). Summaries and interview
angles are original editorial notes (not verbatim PR copy). Public sources only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "policies.json"
LOG_PATH = ROOT / "scripts" / "last_refresh.json"

HK_TZ = timezone(timedelta(hours=8))
USER_AGENT = "JRE-PolicyBank/1.0 (+local educational refresh; public info.gov.hk only)"
BASE = "https://www.info.gov.hk"

# --- filter keywords ---------------------------------------------------------

KEEP_RE = re.compile(
    r"房屋|公屋|簡約公屋|居屋|土地|賣地|收地|發展局|北部都會|新發展區|河套|"
    r"財經|金融|金管局|人民幣|債券|財政司|庫務|稅務|預算|"
    r"醫務|衞生|衛生|藥物|醫療|醫院管理局|醫管局|基層醫療|"
    r"勞工|福利|扶貧|精準扶貧|共創|幸匯|最低工資|強積金|外傭|補充勞工|"
    r"創科|創新科技|工業|人工智能|智能|數碼港|科技園|新型工業|微電子|"
    r"條例草案|刊憲|立法會|施政報告|五年規劃|"
    r"政務司|行政長官|管治|政策|規劃署|產業|物流|運輸及物流|"
    r"大灣區|跨境|口岸|基建|鐵路|調解|知識產權|業權註冊|"
    r"公務員|選舉委員會|律政|司法|"
    r"Housing|Land sale|Finance|Monetary|Health Bureau|Labour|"
    r"Welfare|Innovation|Northern Metropolis|Policy Address|"
    r"Bill 20|gazett|Treasury|fintech|MPF|title registration",
    re.I,
)

DROP_RE = re.compile(
    r"泳灘|紅旗|黃旗|天氣警告|熱帶氣旋|颱風|暴雨|"
    r"獎牌|亞運|殘運|奧運|演唱會|電影節|演藝|慈善放映|"
    r"走私|私煙|冒牌|食安中心檢出|檢獲約|毒品|"
    r"哀悼|訃告|悼念|離世|"
    r"交通意外|被控|謀殺|搶劫|判囚|罰款逾|罪成|"
    r"重陽節翌日假期.*門診|家庭醫學門診服務安排|"
    r"可疑電郵|聖誕.*郵件|攤位拍賣|年宵|"
    r"beach|red flag|weather|typhoon|medal|concert|obituar|"
    r"smuggl|counterfeit|drug trafficking|jailed for|"
    r"Air Quality Health Index|Christmas air mail|fair stalls|^附件$|^Appendix$|國際刑警組織.*全體大會|瀕危物種|endangered species",
    re.I,
)

# Routine single-case health notices (keep outbreak strategy / policy pieces)
ROUTINE_CASE_RE = re.compile(
    r"錄得一宗|調查一宗|公布.*個案最新情況|侵入性肺炎球菌|退伍軍人病個案|"
    r"類鼻疽個案|猴痘確診個案|不明原因嚴重肺炎",
    re.I,
)

DEPT_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ceo", re.compile(r"行政長官|特首|Chief Executive|\bCE\b")),
    ("csso", re.compile(r"政務司|精準扶貧委員會|扶貧專責|幸匯|共創香港|Commission on Targeted Poverty")),
    ("fso", re.compile(r"財政司司長|\bFS\b|Financial Secretary")),
    ("devb", re.compile(r"發展局|賣地|收地|新發展區|北部都會|業權註冊|Development Bureau")),
    ("landsd", re.compile(r"地政總署|收地及徵用|Lands Department")),
    ("hb", re.compile(r"房屋局|簡約公屋|公屋|房委會|Housing Bureau|Housing Authority")),
    ("fstb", re.compile(r"財經事務及庫務局|庫務局|稅務（修訂）|稅務\(修訂\)|印花稅|避免雙重課稅|加密資產|Financial Services and the Treasury|Inland Revenue")),
    ("hkma", re.compile(r"金管局|香港金融管理局|CMU|債務工具中央結算|HKMA|Exchange Fund")),
    ("hhb", re.compile(r"醫務衞生局|醫務衛生局|Health Bureau|Secretary for Health")),
    ("dh", re.compile(r"衛生署|衞生署|衞生防護中心|藥物及醫療器械|Department of Health|\bDH\b|\bCHP\b")),
    ("ha", re.compile(r"醫院管理局|醫管局|Hospital Authority")),
    ("itib", re.compile(r"創新科技及工業局|創科局|新型工業|InnoHK|SITI|ITIB")),
    ("lwb", re.compile(r"勞工及福利局|勞工處|強積金|外籍家庭傭工|補充勞工|Labour")),
    ("tlb", re.compile(r"運輸及物流局|運輸署|航運|口岸|跨境|Transport and Logistics|\bSTL\b")),
    ("cedb", re.compile(r"商務及經濟發展局|商經局|工業貿易|CEDB")),
    ("doj", re.compile(r"律政司|調解\(修訂\)|司法文書|Department of Justice|\bSJ\b")),
    ("legco", re.compile(r"立法會|LegCo|條例草案.*提交")),
    ("sb", re.compile(r"保安局|Security Bureau")),
    ("hyab", re.compile(r"民政及青年事務局|青年實習|HYAB")),
    ("eeb", re.compile(r"環境及生態局|Environment and Ecology")),
    ("investHK", re.compile(r"投資推廣署|InvestHK|Invest Hong Kong")),
]

THEME_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("northern-metropolis", re.compile(r"北部都會|新田|牛潭尾|洪水橋|河套|Northern Metropolis")),
    ("housing-land", re.compile(r"房屋|公屋|簡約公屋|土地|賣地|收地|業權註冊|Housing|land sale")),
    ("finance", re.compile(r"金融|財經|金管局|人民幣|債券|稅務|財政司|Exchange Fund|Treasury")),
    ("fintech-ai", re.compile(r"人工智能|AI|金融科技|數智|智能體|fintech")),
    ("healthcare", re.compile(r"醫療|衞生|衛生|藥物|醫院|基層醫療|Health|MPOX|流感")),
    ("innovation", re.compile(r"創科|創新科技|新型工業|科技園|數碼港|知識產權|微電子|I&T")),
    ("poverty-welfare", re.compile(r"扶貧|福利|幸匯|共創|照顧者|劏房|安老|高齡化|Welfare|poverty")),
    ("labour", re.compile(r"勞工|最低工資|強積金|外傭|補充勞工|MPF|Labour")),
    ("legislation", re.compile(r"條例草案|刊憲|附屬法例|Bill |gazett")),
    ("governance", re.compile(r"施政報告|五年規劃|行政長官|政務司|管治|選舉|大灣區|Policy Address")),
    ("transport-logistics", re.compile(r"運輸|物流|航運|口岸|跨境|鐵路|機場|港口")),
]

NEW_DEPTS = {
    "fso": {"id": "fso", "zh": "財政司司長辦公室", "en": "Financial Secretary's Office"},
    "tlb": {"id": "tlb", "zh": "運輸及物流局", "en": "Transport and Logistics Bureau"},
    "cedb": {"id": "cedb", "zh": "商務及經濟發展局", "en": "Commerce and Economic Development Bureau"},
    "ha": {"id": "ha", "zh": "醫院管理局", "en": "Hospital Authority"},
    "sb": {"id": "sb", "zh": "保安局", "en": "Security Bureau"},
    "hyab": {"id": "hyab", "zh": "民政及青年事務局", "en": "Home and Youth Affairs Bureau"},
    "eeb": {"id": "eeb", "zh": "環境及生態局", "en": "Environment and Ecology Bureau"},
    "investHK": {"id": "investHK", "zh": "投資推廣署", "en": "Invest Hong Kong"},
}

NEW_THEMES = {
    "transport-logistics": {
        "id": "transport-logistics",
        "zh": "運輸與物流",
        "en": "Transport & Logistics",
    },
}


def now_hk() -> datetime:
    return datetime.now(HK_TZ)


def fetch(url: str, timeout: int = 30) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset)
        except LookupError:
            text = raw.decode("utf-8", "replace")
        return text, resp.geturl()


def abs_url(href: str) -> str:
    if href.startswith("http"):
        return href.split("#")[0]
    if href.startswith("/"):
        return BASE + href.split("#")[0]
    return BASE + "/gia/general/" + href.split("#")[0]


def pid_of(url: str) -> str | None:
    m = re.search(r"(P20\d+)", url)
    return m.group(1) if m else None


def day_index_urls(d: date) -> list[str]:
    yyyymm = d.strftime("%Y%m")
    dd = d.strftime("%d")
    # Prefer Chinese index; fall back to English / today
    urls = [
        f"{BASE}/gia/general/{yyyymm}/{dd}c.htm",
        f"{BASE}/gia/general/{yyyymm}/{dd}.htm",
    ]
    if d == now_hk().date():
        urls.insert(0, f"{BASE}/gia/general/today.htm")
    return urls


def parse_day_index(html: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("ul.list a[href], a.NEW[href], a[href*='P20']"):
            href = a.get("href") or ""
            if not re.search(r"P20\d+\.htm", href):
                continue
            title = a.get_text(" ", strip=True)
            title = unescape(title).replace("\u200b", "").strip()
            title = re.sub(r"\s+", " ", title)
            if title:
                items.append({"title": title, "url": abs_url(href)})
    else:
        for m in re.finditer(
            r'<a[^>]+href=["\']([^"\']*P20\d+\.htm)["\'][^>]*>(.*?)</a>',
            html,
            re.I | re.S,
        ):
            href, inner = m.group(1), m.group(2)
            title = unescape(re.sub(r"<[^>]+>", "", inner))
            title = re.sub(r"\s+", " ", title).replace("\u200b", "").strip()
            if title:
                items.append({"title": title, "url": abs_url(href)})
    # dedupe by url keeping first (CN page usually listed once)
    seen: set[str] = set()
    out = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    return out


def extract_article(html: str) -> tuple[str, str]:
    """Return (title, body_text)."""
    title = ""
    body = ""
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        # Prefer <title> — h2 is often just 「附件」 on gazette attachment pages
        if soup.title:
            t = unescape(re.sub(r"\s+", " ", soup.title.get_text(" ", strip=True)))
            t = re.sub(r"\s*[-|].*$", "", t).strip()
            if t and "Press Releases" not in t and "新聞公報" not in t and t not in ("附件", "Appendix"):
                title = t
        if not title:
            for sel in ["h1", ".titleFont", "#title", "h2"]:
                node = soup.select_one(sel)
                if not node:
                    continue
                # skip attachment section headings
                classes = " ".join(node.get("class") or [])
                if "attType" in classes:
                    continue
                t = unescape(re.sub(r"\s+", " ", node.get_text(" ", strip=True)))
                if t and t not in ("附件", "Appendix") and "Press Releases" not in t:
                    title = t
                    break
        pr = soup.select_one("#pressrelease")
        if pr:
            for bad in pr.select("script, style"):
                bad.decompose()
            body = pr.get_text("\n", strip=True)
        if not body:
            main = soup.select_one("#contentBody") or soup.body
            if main:
                body = main.get_text("\n", strip=True)
    else:
        mt = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        if mt:
            title = unescape(re.sub(r"<[^>]+>", "", mt.group(1)))
            title = re.sub(r"\s*[-|].*$", "", title).strip()
        m = re.search(
            r'id=["\']pressrelease["\'][^>]*>(.*?)</div>\s*<div',
            html,
            re.I | re.S,
        )
        if m:
            body = unescape(re.sub(r"<[^>]+>", "\n", m.group(1)))

    body = unescape(body)
    body = body.replace("\u3000", " ").replace("\xa0", " ")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    # trim footer noise
    body = re.split(r"\n\s*完\s*\n", body)[0].strip()
    body = re.sub(
        r"\n?\s*\d{4}年\d{1,2}月\d{1,2}日（星期.）\s*$", "", body
    ).strip()
    return title, body


def policy_score(title: str) -> int:
    if DROP_RE.search(title):
        return -100
    if not KEEP_RE.search(title):
        return -50
    if ROUTINE_CASE_RE.search(title):
        return 5
    score = 20
    boosts = [
        (40, r"條例草案|刊憲|附屬法例"),
        (35, r"北部都會|新發展區|河套"),
        (35, r"簡約公屋|賣地|收地|公營房屋"),
        (30, r"施政報告|五年規劃"),
        (30, r"金管局|人民幣國債|稅務"),
        (28, r"創科|新型工業|人工智能"),
        (28, r"扶貧|幸匯|共創|福利項目"),
        (25, r"強積金|最低工資|補充勞工"),
        (22, r"藥物|「1\+」|醫療產品監管"),
        (18, r"大灣區|跨境|口岸"),
        (15, r"調解|業權註冊|知識產權"),
        (10, r"致辭|會面|出席"),
    ]
    for pts, pat in boosts:
        if re.search(pat, title, re.I):
            score += pts
    # demote pure ceremony / routine ops / thin media standups
    if re.search(r"開幕儀式|頒授典禮|頒獎|酒會|嘉許禮", title):
        score -= 15
    if re.search(r"會見傳媒談話內容|會見傳媒開場發言|開場發言（只有中文）", title):
        score -= 25
    if re.search(r"個案|門診服務安排|交通及運輸安排|瀕危物種", title):
        score -= 10
    return score


def is_policy_relevant(title: str) -> bool:
    return policy_score(title) >= 25


def map_departments(title: str, body: str) -> list[str]:
    text = f"{title}\n{body}"
    found: list[str] = []
    for did, rx in DEPT_RULES:
        if rx.search(text):
            found.append(did)
    # de-prioritize overly broad ceo if other cabinets present
    if len(found) > 2 and "ceo" in found and not re.search(
        r"行政長官|特首", title
    ):
        found = [x for x in found if x != "ceo"]
    return found[:3] or ["csso"]


def map_themes(title: str, body: str) -> list[str]:
    text = f"{title}\n{body}"
    found: list[str] = []
    for tid, rx in THEME_RULES:
        if rx.search(text):
            found.append(tid)
    return found[:3] or ["governance"]


def clean_title(title: str) -> str:
    t = title
    t = re.sub(r"（只有中文）", "", t)
    t = re.sub(r"（附圖(?:[／/]短片)?）", "", t)
    t = re.sub(r"（附短片）", "", t)
    t = re.sub(r"（附圖）", "", t)
    t = re.sub(r"\(with photos?(?:/video)?\)", "", t, flags=re.I)
    t = re.sub(r"\(English only\)", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ：:.-")
    return t


def first_paragraphs(body: str, max_chars: int = 900) -> str:
    # Prefer Chinese full-width paragraphs
    parts = [p.strip() for p in re.split(r"\n+", body) if p.strip()]
    # drop leading photo/credit lines
    filtered = []
    for p in parts:
        if re.match(r"^(相片|Photo|圖說)", p):
            continue
        if len(p) < 12:
            continue
        filtered.append(p)
    buf = ""
    for p in filtered:
        if not buf:
            buf = p
        elif len(buf) + len(p) < max_chars:
            buf += p if buf.endswith("。") else (" " + p)
        else:
            break
    return buf


def _fact_bits(text: str) -> list[str]:
    """Pull compact factual nuggets for an editorial rewrite."""
    bits: list[str] = []
    for rx in [
        r"二○二[一二三四五六七八九零〇0-9]{1,4}年[^，。；]{0,40}",
        r"20\d{2}年\d{1,2}月\d{1,2}日[^，。；]{0,30}",
        r"約?[\d,，]+(?:萬|億|%|個|宗|款|公頃|伙|單位|床位)",
        r"《[^》]{2,40}》",
        r"「[^」]{2,30}」",
    ]:
        for m in re.finditer(rx, text):
            bits.append(m.group(0).strip())
            if len(bits) >= 8:
                return bits
    return bits


def draft_summary(title: str, body: str) -> str:
    """Original Traditional Chinese editorial summary (not a PR dump)."""
    ct = clean_title(title)
    gist = first_paragraphs(body, 650)
    sentences = [s.strip() for s in re.split(r"(?<=[。！？])", gist) if s.strip()]
    # Take 1–2 source sentences then reframe — avoid dumping the whole release
    src = "".join(sentences[:2]) if sentences else gist[:280]
    src = re.sub(r"\s+", " ", src).strip()
    if len(src) > 280:
        idx = src.rfind("。")
        src = src[: idx + 1] if idx > 120 else src[:280] + "…"

    facts = _fact_bits(title + "。" + body[:1200])
    fact_note = ""
    if facts:
        # keep 2–4 distinctive facts
        uniq = []
        for f in facts:
            if f not in uniq and f not in ct:
                uniq.append(f)
            if len(uniq) >= 4:
                break
        if uniq:
            fact_note = "要點包括：" + "；".join(uniq[:4]) + "。"

    if re.search(r"動議二讀|發言全文", ct):
        lead = f"立法進程：「{ct}」。宜抽出草案目的、主要修訂及為何現在提交。"
    elif re.search(r"條例草案|刊憲|附屬法例", ct + src):
        lead = f"政府就「{ct}」推出／推進立法或附屬法例安排。"
    elif re.search(r"致辭|開幕|會面|出席", ct):
        lead = f"「{ct}」反映相關政策推廣或區域合作取態，面試宜抓可驗證主張而非禮節性表述。"
    elif re.search(r"簡約公屋|賣地|收地|房屋|土地", ct + src):
        lead = f"房屋／土地政策動態：「{ct}」。"
    elif re.search(r"金管局|金融|稅務|人民幣", ct + src):
        lead = f"財金政策動態：「{ct}」。"
    elif re.search(r"創科|工業|人工智能|科技", ct + src):
        lead = f"創科／產業政策動態：「{ct}」。"
    elif re.search(r"扶貧|福利|勞工|強積金", ct + src):
        lead = f"民生／勞工福利政策動態：「{ct}」。"
    else:
        lead = f"政策相關公報：「{ct}」。"

    # Paraphrase body into a short clause (strip leading "政府今日…" boilerplate lightly)
    paraphrase = src
    paraphrase = re.sub(r"^政府今日（[^）]+）", "當局", paraphrase)
    paraphrase = re.sub(r"^The Government announced today[^.]*\.\s*", "", paraphrase)
    # drop long name/list dumps (companies, attendees)
    if paraphrase.count("有限公司") >= 3 or paraphrase.count("Limited") >= 3:
        paraphrase = re.split(r"名單如下[:：]", paraphrase)[0]
        paraphrase = re.sub(r"(?:有限公司|Limited).*$", "等機構。", paraphrase, count=1)
    body_bit = paraphrase
    if body_bit and not body_bit.endswith(("。", "…", ".", "！", "？")):
        body_bit += "。"

    summary = lead
    if body_bit and body_bit not in lead:
        summary += body_bit
    if fact_note and fact_note not in summary:
        summary += fact_note
    # hard cap
    if len(summary) > 480:
        idx = summary.rfind("。", 0, 480)
        summary = summary[: idx + 1] if idx > 200 else summary[:480] + "…"
    return summary


def draft_angles(title: str, body: str, themes: list[str], depts: list[str]) -> list[str]:
    angles: list[str] = []
    t = clean_title(title)
    blob = title + body

    if "legislation" in themes or re.search(r"條例草案|刊憲|附屬法例", blob):
        angles.append("條例／附屬法例的政策目標是什麼？與現行制度相比，簡化了哪些程序，又削弱了哪些制衡？")
        angles.append("若立法會或業界反對關鍵條文，政府有何備選方案及時間表？")
    if "northern-metropolis" in themes or re.search(r"北部都會", blob):
        angles.append("此舉如何具體加快北部都會區「熟地」供應或產業進駐？成效應以什麼指標衡量？")
    if "housing-land" in themes:
        angles.append("房屋／土地措施如何與公營房屋、私人市場及北部都會區供應銜接？")
        angles.append("若市場反應冷淡或申請遠超供應，政府會如何調整優先次序？")
    if "finance" in themes or "fintech-ai" in themes:
        angles.append("對鞏固香港國際金融／離岸人民幣／創科金融中心地位有何實質作用？潛在風險是什麼？")
    if "healthcare" in themes:
        angles.append("措施如何在加快服務／新藥准入與安全把關、公營系統負荷之間取平衡？")
    if "innovation" in themes:
        angles.append("如何避免「有政策、缺落地」？場景驗證、資助成效與人才留港應如何考核？")
    if "poverty-welfare" in themes or "labour" in themes:
        angles.append("目標群組是否夠精準？如何避免資源錯配，並確保商界／僱主參與可持續？")
    if "governance" in themes and len(angles) < 2:
        angles.append("活動或公布如何轉化為可量度的政策成果，而非一次性公關？")
    if "transport-logistics" in themes:
        angles.append("跨境／物流安排如何服務大灣區人流物流，同時控制本港社區與基建負荷？")

    # Generic fallbacks tied to title
    if len(angles) < 2:
        angles.append(f"「{t}」的短期執行挑戰是什麼？哪個局／署應負主責？")
    if len(angles) < 3:
        angles.append("若成效未如預期，應在下一份《施政報告》或五年規劃中如何調整？")

    # unique preserve order
    out: list[str] = []
    seen: set[str] = set()
    for a in angles:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out[:3]


def make_id(d: str, url: str, title: str) -> str:
    pid = pid_of(url)
    if pid:
        return f"{d.replace('-', '')}-{pid[-6:].lower()}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:24].strip("-")
    return f"{d.replace('-', '')}-{slug or 'item'}"


def title_fingerprint(title: str) -> str:
    t = clean_title(title)
    t = re.sub(r"[A-Za-z]+", "", t)  # drop english for zh compare
    # normalize near-synonyms / punctuation variants
    for a, b in [
        ("步入", "進入"),
        ("開放接受申請", "接受申請"),
        ("全部項目", ""),
        ("新聞公報", ""),
    ]:
        t = t.replace(a, b)
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "", t)
    return t[:28]


def load_data() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def ensure_taxonomies(data: dict[str, Any], dept_ids: set[str], theme_ids: set[str]) -> None:
    existing_d = {d["id"] for d in data["departments"]}
    existing_t = {t["id"] for t in data["themes"]}
    for did in dept_ids:
        if did not in existing_d and did in NEW_DEPTS:
            data["departments"].append(NEW_DEPTS[did])
            existing_d.add(did)
    for tid in theme_ids:
        if tid not in existing_t and tid in NEW_THEMES:
            data["themes"].append(NEW_THEMES[tid])
            existing_t.add(tid)


def collect_candidates(days: int, errors: list[str]) -> list[dict[str, Any]]:
    today = now_hk().date()
    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for i in range(days):
        d = today - timedelta(days=i)
        day_items: list[dict[str, str]] = []
        for url in day_index_urls(d):
            try:
                html, final = fetch(url)
                day_items = parse_day_index(html)
                if day_items:
                    break
            except Exception as e:  # noqa: BLE001
                errors.append(f"index {url}: {e}")
        for it in day_items:
            if it["url"] in seen_urls:
                continue
            seen_urls.add(it["url"])
            score = policy_score(it["title"])
            if score < 25:
                continue
            collected.append(
                {
                    "date": d.isoformat(),
                    "title": it["title"],
                    "url": it["url"],
                    "score": score,
                }
            )
        time.sleep(0.15)
    collected.sort(key=lambda x: (-x["score"], x["date"]), reverse=False)
    collected.sort(key=lambda x: (-x["score"], x["date"]))
    return collected


def build_existing_keys(data: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    urls: set[str] = set()
    pids: set[str] = set()
    fps: set[str] = set()
    for it in data["items"]:
        u = it.get("source_url") or ""
        urls.add(u)
        p = pid_of(u)
        if p:
            pids.add(p)
            # EN/CN variants often use nearby P numbers on the same day
            try:
                n = int(p[1:])
                for delta in range(-5, 6):
                    if delta:
                        pids.add(f"P{n + delta}")
            except ValueError:
                pass
        fps.add(title_fingerprint(it.get("title") or ""))
        if it.get("title_en"):
            fps.add(title_fingerprint(it["title_en"]))
    return urls, pids, fps


def process_new(
    candidates: list[dict[str, Any]],
    data: dict[str, Any],
    max_new: int,
    errors: list[str],
) -> tuple[list[dict[str, Any]], int]:
    urls, pids, fps = build_existing_keys(data)
    skipped = 0
    added: list[dict[str, Any]] = []

    for cand in candidates:
        if len(added) >= max_new:
            break
        u = cand["url"]
        p = pid_of(u)
        fp = title_fingerprint(cand["title"])
        if u in urls or (p and p in pids) or (fp and fp in fps):
            skipped += 1
            continue
        # soft near-dup: fingerprint prefix overlap with existing
        if fp and any(fp[:16] and (fp[:16] in old or old[:16] in fp) for old in fps if old):
            skipped += 1
            continue
        # fetch article
        try:
            html, final = fetch(u)
            atitle, body = extract_article(html)
            time.sleep(0.2)
        except Exception as e:  # noqa: BLE001
            errors.append(f"article {u}: {e}")
            skipped += 1
            continue

        raw_title = atitle or ""
        if not raw_title or raw_title in ("附件", "Appendix") or len(raw_title) < 8:
            raw_title = cand["title"]
        title = clean_title(raw_title)
        if not title or title in ("附件", "Appendix") or len(title) < 8:
            errors.append(f"bad title {u}")
            skipped += 1
            continue
        if not body or len(body) < 40:
            errors.append(f"thin body {u}")
            skipped += 1
            continue
        # Skip attachment-only / privilege-order fluff even if scored earlier
        if re.search(r"國際刑警組織.*全體大會|^附件$", title):
            skipped += 1
            continue

        # Prefer Chinese content; if page is English-only and we have no zh, still allow
        depts = map_departments(title, body)
        themes = map_themes(title, body)
        summary = draft_summary(title, body)
        angles = draft_angles(title, body, themes, depts)
        item = {
            "id": make_id(cand["date"], final, title),
            "date": cand["date"],
            "title": title,
            "departments": depts,
            "themes": themes,
            "summary": summary,
            "interview_angles": angles,
            "source_url": final,
            "source_name": "info.gov.hk 新聞公報",
        }
        added.append(item)
        urls.add(final)
        if p:
            pids.add(p)
        if fp:
            fps.add(fp)

    return added, skipped


def merge_items(data: dict[str, Any], new_items: list[dict[str, Any]]) -> None:
    dept_ids: set[str] = set()
    theme_ids: set[str] = set()
    for it in new_items:
        dept_ids.update(it["departments"])
        theme_ids.update(it["themes"])
    ensure_taxonomies(data, dept_ids, theme_ids)

    # prepend new, then sort all by date desc, stable by id
    combined = new_items + data["items"]
    # dedupe by source_url just in case
    seen: set[str] = set()
    uniq = []
    for it in combined:
        u = it.get("source_url")
        if u in seen:
            continue
        seen.add(u)
        uniq.append(it)
    uniq.sort(key=lambda x: (x.get("date") or "", x.get("id") or ""), reverse=True)
    data["items"] = uniq
    data["meta"]["updated"] = now_hk().date().isoformat()


def write_log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh JRE Policy Bank from info.gov.hk")
    parser.add_argument("--days", type=int, default=7, help="How many recent days to scan")
    parser.add_argument("--max-new", type=int, default=10, help="Max new items to add this run")
    parser.add_argument("--dry-run", action="store_true", help="Do not write policies.json")
    args = parser.parse_args(argv)

    errors: list[str] = []
    started = now_hk().isoformat()

    if not DATA_PATH.exists():
        print(f"Missing {DATA_PATH}", file=sys.stderr)
        return 1

    data = load_data()
    print(f"Loaded {len(data['items'])} existing items from {DATA_PATH}")

    candidates = collect_candidates(args.days, errors)
    print(f"Policy-relevant candidates: {len(candidates)}")

    # If today is thin, we already scan --days; still try to add several
    new_items, skipped = process_new(candidates, data, args.max_new, errors)
    print(f"New to add: {len(new_items)}; skipped/dup/failed: {skipped}")

    if new_items and not args.dry_run:
        merge_items(data, new_items)
        DATA_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {DATA_PATH} (total items={len(data['items'])})")
    elif args.dry_run:
        print("Dry run — no write")
    else:
        # still bump meta.updated to show refresh attempted
        data["meta"]["updated"] = now_hk().date().isoformat()
        DATA_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("No new items; meta.updated refreshed")

    log = {
        "ran_at": started,
        "timezone": "Asia/Hong_Kong",
        "days_scanned": args.days,
        "candidates": len(candidates),
        "added_count": len(new_items),
        "skipped_count": skipped,
        "errors": errors,
        "added_ids": [x["id"] for x in new_items],
        "added_titles": [x["title"] for x in new_items],
    }
    write_log(log)
    print(f"Log: {LOG_PATH}")
    for t in log["added_titles"]:
        print(f"  + {t}")
    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors[:12]:
            print(f"  ! {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
