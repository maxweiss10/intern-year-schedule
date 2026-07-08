#!/usr/bin/env python3
"""Convert the QGenda iCal feed into schedule-live.json for the schedule page.

Reads the feed URL from the ICS_URL env var (a repo secret in CI) so the
personal calendar key never appears in the repo.
"""
import json, os, re, sys, urllib.request
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "schedule-live.json")

url = os.environ["ICS_URL"]
raw = urllib.request.urlopen(url, timeout=60).read().decode("utf-8", "replace")

# unfold continuation lines (RFC 5545)
lines, cur = [], ""
for ln in raw.splitlines():
    if ln[:1] in (" ", "\t"):
        cur += ln[1:]
    else:
        if cur:
            lines.append(cur)
        cur = ln
if cur:
    lines.append(cur)

def parse_dt(prop):
    """Return (date_iso, hhmm_local or None) for a DTSTART/DTEND property line."""
    name, _, val = prop.partition(":")
    if "VALUE=DATE" in name:
        return f"{val[0:4]}-{val[4:6]}-{val[6:8]}", None
    m = re.match(r"(\d{8})T(\d{6})(Z?)", val)
    if not m:
        return None, None
    d, t, z = m.groups()
    dt = datetime.strptime(d + t, "%Y%m%d%H%M%S")
    if z:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(TZ)
    else:
        tzid = re.search(r"TZID=([^;:]+)", name)
        dt = dt.replace(tzinfo=ZoneInfo(tzid.group(1)) if tzid else TZ).astimezone(TZ)
    return dt.date().isoformat(), dt.strftime("%H:%M")

events, ev = [], None
for ln in lines:
    if ln == "BEGIN:VEVENT":
        ev = {}
    elif ln == "END:VEVENT" and ev is not None:
        if ev.get("d") and ev.get("t"):
            events.append(ev)
        ev = None
    elif ev is not None:
        if ln.startswith("DTSTART"):
            ev["d"], s = parse_dt(ln)
            if s:
                ev["s"] = s
        elif ln.startswith("DTEND") and "T" in ln.split(":", 1)[-1]:
            _, e = parse_dt(ln)
            if e:
                ev["e"] = e
        elif ln.startswith("SUMMARY"):
            t = ln.split(":", 1)[1]
            t = t.replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
            t = re.sub(r"\s*\[Weiss, M\]\s*$", "", t).strip()
            if t.startswith("[R] "):
                ev["r"] = 1
                t = t[4:]
            ev["t"] = t

events.sort(key=lambda e: (e["d"], 0 if e.get("r") else 1, e.get("s") or ""))
out = {
    "updated": datetime.now(TZ).strftime("%Y-%m-%d %H:%M %Z"),
    "events": events,
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
print(f"wrote {len(events)} events, {events[0]['d']} .. {events[-1]['d']}")
