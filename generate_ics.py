from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

# =========================
# Einstellungen
# =========================

CLUB_URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I#!/"

CALENDAR_NAME = "FV Neuhausen Vereinsspielplan"
TIMEZONE = "Europe/Berlin"

# Wie lange ein Spiel im Kalender blockiert werden soll.
DEFAULT_EVENT_DURATION_HOURS = 2

# Sicherheitspuffer: FUSSBALL.DE zeigt meist ohnehin nur einen gewissen Zeitraum.
# Das Script behält gefundene Spiele bis X Tage in die Zukunft.
DAYS_AHEAD = 220

OUTPUT_FILE = "vereinsspielplan.ics"

# =========================
# Parser
# =========================

WEEKDAYS_LONG = r"(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)"
DATE_HEADER_RE = re.compile(
    rf"^{WEEKDAYS_LONG},\s*(\d{{2}}\.\d{{2}}\.\d{{4}})\s*-\s*(\d{{1,2}}:\d{{2}})\s*Uhr\s*\|\s*(.+?)\s*\|\s*(.+?)$"
)

# Beispiel: "ME | 356849016"
GAME_NO_RE = re.compile(r"\b(ME|FS|PO|TU|HM|FT|PR)\s*\|\s*(\d{6,})\b")

TEAM_KEYWORDS = ("FV", "SGM", "TSV", "VfB", "TB ", "SF ", "FC ", "SV ", "TSG", "GSV", "1. FC", "Spfr", "Neuhausen")


@dataclass(frozen=True)
class Match:
    start: datetime
    competition: str
    match_type: str
    home: str
    away: str
    game_no: str | None
    source_url: str

    @property
    def title(self) -> str:
        return f"{self.home} vs. {self.away}"

    @property
    def uid(self) -> str:
        base = f"{self.game_no or ''}|{self.start.isoformat()}|{self.home}|{self.away}"
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
        return f"{digest}@fvn-fussballde-calendar"


def normalize_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = value.replace("\u200b", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def looks_like_team(value: str) -> bool:
    if not value or len(value) < 3:
        return False
    if value in {"Zum Spiel", "Legende", "Anzeige"}:
        return False
    if "|" in value:
        return False
    return any(keyword in value for keyword in TEAM_KEYWORDS)


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def parse_matches(html: str, source_url: str) -> list[Match]:
    soup = BeautifulSoup(html, "html.parser")

    # FUSSBALL.DE liefert die Daten aktuell bereits im HTML mit.
    # Die Optik lädt zwar dynamisch, aber im Quelltext steht eine Textversion.
    lines = [
        normalize_text(line)
        for line in soup.get_text("\n", strip=True).split("\n")
        if normalize_text(line)
    ]

    tz = ZoneInfo(TIMEZONE)
    matches: list[Match] = []

    for idx, line in enumerate(lines):
        header_match = DATE_HEADER_RE.match(line)
        if not header_match:
            continue

        date_str = header_match.group(2)
        time_str = header_match.group(3)
        category = normalize_text(header_match.group(4))
        league = normalize_text(header_match.group(5))

        start = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M").replace(tzinfo=tz)

        # Die Detailzeilen zum Spiel stehen nach der Header-Zeile.
        nearby = lines[idx + 1 : idx + 18]

        game_no = None
        match_type = ""
        for item in nearby:
            no_match = GAME_NO_RE.search(item)
            if no_match:
                match_type = no_match.group(1)
                game_no = no_match.group(2)
                break

        # In der Textversion stehen die beiden Mannschaftsnamen meist als einzelne Links.
        teams = [item for item in nearby if looks_like_team(item)]

        # Doppelte Teamnamen in engem Kontext entfernen, Reihenfolge beibehalten.
        unique_teams: list[str] = []
        for team in teams:
            if team not in unique_teams:
                unique_teams.append(team)

        if len(unique_teams) < 2:
            print(f"WARNUNG: Mannschaften nicht erkannt bei {line}")
            continue

        home, away = unique_teams[0], unique_teams[1]
        competition = f"{category} | {league}"

        matches.append(
            Match(
                start=start,
                competition=competition,
                match_type=match_type,
                home=home,
                away=away,
                game_no=game_no,
                source_url=source_url,
            )
        )

    # Doppelte Spiele entfernen
    deduped = {match.uid: match for match in matches}
    result = sorted(deduped.values(), key=lambda match: match.start)

    now = datetime.now(ZoneInfo(TIMEZONE)) - timedelta(days=2)
    latest = datetime.now(ZoneInfo(TIMEZONE)) + timedelta(days=DAYS_AHEAD)
    return [match for match in result if now <= match.start <= latest]


def build_calendar(matches: list[Match]) -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//FV Neuhausen Vereinsspielplan//fussball.de//DE")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", CALENDAR_NAME)
    cal.add("x-wr-timezone", TIMEZONE)
    cal.add("x-published-ttl", "PT24H")

    generated_at = datetime.now(ZoneInfo(TIMEZONE))

    for match in matches:
        event = Event()
        event.add("uid", match.uid)
        event.add("summary", match.title)
        event.add("dtstart", match.start)
        event.add("dtend", match.start + timedelta(hours=DEFAULT_EVENT_DURATION_HOURS))
        event.add("dtstamp", generated_at)
        event.add(
            "description",
            "\n".join(
                [
                    match.competition,
                    f"Spielart: {match.match_type}" if match.match_type else "",
                    f"Spielnummer: {match.game_no}" if match.game_no else "",
                    f"Quelle: {match.source_url}",
                ]
            ).strip(),
        )
        event.add("url", match.source_url)

        cal.add_component(event)

    return cal


def main() -> None:
    html = fetch_html(CLUB_URL)
    matches = parse_matches(html, CLUB_URL)

    if not matches:
        raise RuntimeError(
            "Keine Spiele gefunden. Vermutlich hat FUSSBALL.DE die HTML-Struktur geändert "
            "oder aktuell keine Spiele im Vereinsspielplan sichtbar."
        )

    cal = build_calendar(matches)
    with open(OUTPUT_FILE, "wb") as file:
        file.write(cal.to_ical())

    print(f"{len(matches)} Spiele nach {OUTPUT_FILE} exportiert.")
    for match in matches[:10]:
        print(f"- {match.start:%d.%m.%Y %H:%M}: {match.title}")


if __name__ == "__main__":
    main()
