"""Turn one calendar event row into a shareable .ics file (RFC 5545).

Import exists in three flavors; this is the missing symmetric half. One row
becomes one VEVENT deliberately: recurring series are materialized as
individual rows here (an RRULE would double-book against the sibling rows on
re-import, and could not express the observance skips), so sharing an event
shares exactly the occurrence you clicked. Times are written as floating
local date-times — the store keeps local "HH:MM" with no timezone, and
inventing a TZID the data doesn't have would shift the event for the
recipient.
"""
from __future__ import annotations

import datetime


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 folding: lines over 75 octets continue with CRLF + space."""
    out, s = [], line.encode()
    while len(s) > 75:
        cut = 75
        while cut > 1 and (s[cut] & 0xC0) == 0x80:   # don't split a UTF-8 char
            cut -= 1
        out.append(s[:cut].decode())
        s = b" " + s[cut:]
    out.append(s.decode())
    return "\r\n".join(out)


def _dt(date_str: str, time_str: str) -> str:
    d = datetime.date.fromisoformat(date_str)
    hh, mm = (time_str or "00:00").split(":")[:2]
    return f"{d:%Y%m%d}T{int(hh):02d}{int(mm):02d}00"


def event_to_ics(row: dict) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MACalendar//EN",
        "BEGIN:VEVENT",
        f"UID:macalendar-{row['id']}@local",
        f"DTSTAMP:{datetime.datetime.now():%Y%m%dT%H%M%S}",
        f"DTSTART:{_dt(row['date'], row['start_time'])}",
    ]
    if row.get("end_time"):
        lines.append(f"DTEND:{_dt(row['date'], row['end_time'])}")
    lines.append(f"SUMMARY:{_escape(row['title'])}")
    if row.get("location"):
        lines.append(f"LOCATION:{_escape(row['location'])}")
    desc = row.get("description", "")
    if row.get("attendees"):
        desc = (desc + "\n" if desc else "") + f"With: {row['attendees']}"
    if desc:
        lines.append(f"DESCRIPTION:{_escape(desc)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def filename_for(row: dict) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in row["title"].lower()).strip("-")
    return f"{slug[:40] or 'event'}.ics"
