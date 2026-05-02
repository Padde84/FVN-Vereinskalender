import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event

CLUB_URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I"
LOCAL_TZ = tz.gettz("Europe/Berlin")

# Erstmal ALLE Neuhausen-Spiele, nicht nur Heimspiele.
# Wenn das läuft, können wir danach wieder auf reine Heimspiele filtern.
ONLY_NEUHAUSEN_INVOLVED = True

headers = {"User-Agent": "Mozilla/5.0"}

now = datetime.now(LOCAL_TZ)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

end_date = datetime(now.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if now > end_date:
    end_date = datetime(now.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

from_api = today_start.strftime("%Y-%m-%d")
to_api = end_date.strftime("%Y-%m-%d")

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Spiele")
cal.add("x-wr-timezone", "Europe/Berlin")


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def parse_datetime(date_str, time_str):
    fmt = "%d.%m.%y %H:%M" if len(date_str.split(".")[-1]) == 2 else "%d.%m.%Y %H:%M"
    return datetime.strptime(f"{date_str} {time_str}", fmt).replace(tzinfo=LOCAL_TZ)


def get_team_ids():
    html = requests.get(CLUB_URL, headers=headers, timeout=30).text
    ids = sorted(set(re.findall(r"team-id/([A-Z0-9]+)", html)))
    print(f"Team-IDs gefunden: {len(ids)}")
    return ids


def fetch_team_html(team_id):
    url = f"https://www.fussball.de/ajax.team.matchplan/-/mime-type/HTML/show-venues/true/team-id/{team_id}"
    params = {
        "datum-von": from_api,
        "datum-bis": to_api,
        "match-type": "-1",
        "wettkampftyp": "-1",
    }
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.text


def extract_matches_from_html(html, source_id):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [clean(x) for x in text.splitlines() if clean(x)]

    matches = []

    header_pattern = re.compile(
        r"^(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag),\s*"
        r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{1,2}:\d{2})\s*Uhr\s*\|\s*(.+)$"
    )

    for i, line in enumerate(lines):
        m = header_pattern.match(line)
        if not m:
            continue

        date_str = m.group(2)
        time_str = m.group(3)
        competition = m.group(4)

        start = parse_datetime(date_str, time_str)

        if not (today_start <= start <= end_date):
            continue

        block = " ".join(lines[i:i + 8])
        block = clean(block)

        if ONLY_NEUHAUSEN_INVOLVED and "neuhausen" not in block.lower():
            continue

        team_line = ""
        for candidate in lines[i + 1:i + 8]:
            if " : " in candidate and "Zum Spiel" in candidate:
                team_line = candidate
                break

        if not team_line:
            for candidate in lines[i + 1:i + 8]:
                if " : " in candidate:
                    team_line = candidate
                    break

        if not team_line:
            continue

        team_line = clean(team_line)
        team_line = re.sub(r"Zum Spiel.*$", "", team_line).strip()

        parts = team_line.split(" : ", 1)
        if len(parts) != 2:
            continue

        home_team = clean(parts[0])
        away_team = clean(parts[1])

        if "spielfrei" in home_team.lower() or "spielfrei" in away_team.lower():
            continue

        title = f"{home_team} vs. {away_team}"
        uid = f"{source_id}-{title}-{start.isoformat()}@fv-neuhausen"

        matches.append({
            "title": title,
            "start": start,
            "end": start + timedelta(hours=2),
            "competition": competition,
            "location": "",
            "uid": uid,
        })

    return matches


all_matches = {}

# 1) Vereinsspielplan direkt auslesen
club_html = requests.get(CLUB_URL, headers=headers, timeout=30).text
for match in extract_matches_from_html(club_html, "club"):
    all_matches[match["uid"]] = match

print(f"Direkter Vereinsspielplan: {len(all_matches)} Spiele")

# 2) Zusätzlich alle Mannschaftsspielpläne abrufen
team_ids = get_team_ids()

for team_id in team_ids:
    try:
        html = fetch_team_html(team_id)
        matches = extract_matches_from_html(html, team_id)

        for match in matches:
            all_matches[match["uid"]] = match

        print(f"{team_id}: {len(matches)} Spiele")
    except Exception as e:
        print(f"{team_id}: Fehler: {e}")

for item in sorted(all_matches.values(), key=lambda x: x["start"]):
    event = Event()
    event.add("summary", item["title"])
    event.add("dtstart", item["start"])
    event.add("dtend", item["end"])
    event.add("location", item["location"])
    event.add("description", f"{item['competition']}\nQuelle: {CLUB_URL}")
    event.add("uid", item["uid"])
    cal.add_component(event)

with open("vereinsspielplan.ics", "wb") as f:
    f.write(cal.to_ical())

print(f"{len(all_matches)} Spiele bis {end_date.strftime('%d.%m.%Y')} exportiert.")
