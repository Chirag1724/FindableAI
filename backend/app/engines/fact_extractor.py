"""DOM Business Fact Extractor.

Extracts structured business facts (name, contact info, operating hours, FAQs)
directly from crawled HTML and DOM chunks.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.engines.contradiction import (
    _COORD_RE,
    _EMAIL_RE,
    _HOURS_RE,
    _PHONE_RE,
)
from app.schemas.intelligence import EntailmentStatus, IntentEvaluation
from app.schemas.patching import (
    BusinessFacts,
    FaqEntry,
    OpeningHoursFact,
)

logger = logging.getLogger(__name__)

_NORM_DAY_MAP: dict[str, str] = {
    "mon": "Monday",
    "monday": "Monday",
    "tue": "Tuesday",
    "tues": "Tuesday",
    "tuesday": "Tuesday",
    "wed": "Wednesday",
    "wednesday": "Wednesday",
    "thu": "Thursday",
    "thur": "Thursday",
    "thurs": "Thursday",
    "thursday": "Thursday",
    "fri": "Friday",
    "friday": "Friday",
    "sat": "Saturday",
    "saturday": "Saturday",
    "sun": "Sunday",
    "sunday": "Sunday",
}


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split()).strip()


def _normalize_time(raw: str) -> str | None:
    raw = raw.strip().lower()
    m_12 = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", raw)
    if not m_12:
        return None
    hr = int(m_12.group(1))
    mn = int(m_12.group(2) or 0)
    period = m_12.group(3)
    if period == "pm" and hr < 12:
        hr += 12
    elif period == "am" and hr == 12:
        hr = 0
    if 0 <= hr <= 23 and 0 <= mn <= 59:
        return f"{hr:02d}:{mn:02d}"
    return None


def extract_business_facts(
    html: str,
    chunks: Sequence[Any] = (),
    url: str = "",
    intent_evaluations: Sequence[IntentEvaluation] = (),
) -> BusinessFacts:
    """
    Extracts structured business facts from HTML and DOM chunks.
    Only attributes backed by explicit DOM evidence are populated.
    """
    soup = BeautifulSoup(html or "", "lxml")

    # 1. Entity Name
    name: str | None = None
    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site and og_site.get("content"):
        name = _clean_text(str(og_site.get("content")))

    if not name:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            name = _clean_text(str(og_title.get("content")))

    if not name and soup.title and soup.title.string:
        raw_title = soup.title.string
        parts = re.split(r"\s+[|\-\u2013\u2014:]\s+", raw_title)
        candidate = parts[-1] if len(parts) > 1 and len(parts[-1]) < len(parts[0]) else parts[0]
        name = _clean_text(candidate)

    if not name:
        h1 = soup.find("h1")
        if h1:
            name = _clean_text(h1.get_text())

    if not name and url:
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path
        host = re.sub(r"^www\.", "", host.split(":")[0])
        name = host.split(".")[0].capitalize()

    # 2. Telephone
    phone: str | None = None
    tel_link = soup.find("a", href=re.compile(r"^tel:", re.I))
    if tel_link and tel_link.get("href"):
        raw_tel = re.sub(r"^tel:", "", str(tel_link.get("href")), flags=re.I).strip()
        if len(re.sub(r"[^\d+]", "", raw_tel)) >= 7:
            phone = raw_tel

    # 3. Email
    email: str | None = None
    mail_link = soup.find("a", href=re.compile(r"^mailto:", re.I))
    if mail_link and mail_link.get("href"):
        raw_mail = (
            re.sub(r"^mailto:", "", str(mail_link.get("href")), flags=re.I).split("?")[0].strip()
        )
        if _EMAIL_RE.match(raw_mail):
            email = raw_mail

    # 4. Search across DOM chunks for phone, email, coords, hours, address hints
    chunk_texts: list[str] = []
    for c in chunks:
        content = getattr(c, "content", "") or ""
        if content:
            chunk_texts.append(str(content))

    combined_text = "\n".join(chunk_texts) if chunk_texts else (soup.get_text() if soup else "")

    if not phone:
        phone_match = _PHONE_RE.search(combined_text)
        if phone_match:
            phone = phone_match.group(0).strip()

    if not email:
        email_match = _EMAIL_RE.search(combined_text)
        if email_match:
            email = email_match.group(0).strip()

    # 5. Geocoordinates
    lat: float | None = None
    lon: float | None = None
    coord_match = _COORD_RE.search(combined_text)
    if coord_match:
        try:
            parsed_lat = float(coord_match.group("lat"))
            parsed_lon = float(coord_match.group("lon"))
            if -90.0 <= parsed_lat <= 90.0 and -180.0 <= parsed_lon <= 180.0:
                lat = parsed_lat
                lon = parsed_lon
        except (ValueError, TypeError):
            pass

    # 6. Opening hours
    opening_hours: list[OpeningHoursFact] = []
    seen_days: set[str] = set()
    for m in _HOURS_RE.finditer(combined_text):
        raw_day = m.group("day").lower()
        day_norm = _NORM_DAY_MAP.get(raw_day)
        if not day_norm or day_norm in seen_days:
            continue
        opens = _normalize_time(m.group("start"))
        closes = _normalize_time(m.group("end"))
        if opens and closes:
            opening_hours.append(OpeningHoursFact(day_of_week=day_norm, opens=opens, closes=closes))
            seen_days.add(day_norm)

    # 7. FAQs: Extract from <details><summary> or Grounded Intent Evaluations
    faq_entries: list[FaqEntry] = []
    for details in soup.find_all("details"):
        summary = details.find("summary")
        if summary:
            q_text = _clean_text(summary.get_text())
            summary.extract()
            a_text = _clean_text(details.get_text())
            if len(q_text) > 5 and len(a_text) > 5:
                faq_entries.append(FaqEntry(question=q_text, answer=a_text))

    # Also ground high-confidence intents into FAQ entries
    for intent in intent_evaluations:
        if intent.status in (EntailmentStatus.SUPPORTED, EntailmentStatus.PARTIALLY_SUPPORTED):
            if len(intent.query) > 8 and intent.reasoning and len(intent.reasoning) > 10:
                # Deduplicate
                if not any(f.question.lower() == intent.query.lower() for f in faq_entries):
                    faq_entries.append(
                        FaqEntry(
                            question=intent.query,
                            answer=intent.reasoning,
                            source_intent_id=intent.intent_id,
                        )
                    )
        if len(faq_entries) >= 5:
            break

    # Street/locality hints
    street_address: str | None = None
    address_locality: str | None = None
    postal_code: str | None = None

    addr_match = re.search(
        r"(?i)\b(?:address|location|visit us at|located at)\s*[:\-]\s*([^\n\r]{10,80})",
        combined_text,
    )
    if addr_match:
        street_address = _clean_text(addr_match.group(1))

    zip_match = re.search(
        r"\b\d{5}(?:-\d{4})?\b|\b[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2}\b", combined_text
    )
    if zip_match:
        postal_code = zip_match.group(0).strip()

    return BusinessFacts(
        name=name or "Business",
        telephone=phone,
        email=email,
        street_address=street_address,
        address_locality=address_locality,
        postal_code=postal_code,
        latitude=lat,
        longitude=lon,
        opening_hours=opening_hours,
        faq_entries=faq_entries,
    )
