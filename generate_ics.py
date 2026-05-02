import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event

CLUB_URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I"
LOCAL_TZ = tz.gettz("Europe/Berlin")

# -1 = alle Spiele, 1 = Heimspiele, 2 = Auswärtsspiele
MATCH_TYPE = -1

now = datetime.now(LOCAL_TZ)
start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

end_date = datetime(now.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if now > end_date:
    end_date = datetime(now.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

DATE_FROM = start_date.strftime("%Y-%m-%d")
DATE_TO = end_date.strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Spiele")
cal.add("x-wr-timezone", "Europe/Berlin")


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def get_team_ids():
    html = requests.get(CLUB_URL, headers=HEADERS, timeout=30).text
    ids = set(re.findall(r"team-id/([A-Z0-9]+)", html))

    # Fallback: falls IDs anders eingebettet sind
    ids.update(re.findall(r'team-id["\']?\s*[:=/]\s*["\']?([A-Z0-9]{10,})', html))

    return sorted(ids)


def fetch_matchplan(team_id):
    url = (
        "https://www.fussball.de/ajax.team.matchplan/"
        f"-/mime-type/HTML/show-venues/true/team-id/{team_id}"
    )

    params = {
        "datum-von": DATE_FROM,
        "datum-bis": DATE_TO,
        "match-type": str(MATCH_TYPE),
        "wettkampftyp": "-1",
    }

    response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.text


def parse_start(date_text, time_text):
    if len(date_text.split(".")[-1]) == 2:
        fmt = "%d.%m.%y %H:%M"
    else:
        fmt = "%d.%m.%Y %H:%M"

    return datetime.strptime(f"{date_text} {time_text}", fmt).replace(tzinfo=LOCAL_TZ)


def parse_matchplan(html, team_id):
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" ", strip=True))

    pattern = re.compile(
        r"(?:(Mo|Di|Mi|Do|Fr|Sa|So),\s*)?"
        r"(\d{2}\.\d{2}\.\d{2})\s*\|\s*"
        r"(\d{1,2}:\d{2})\s+"
        r"(.+?)\s+"
        r"(ME|FS|PO|TU|HM|FT)\s*\|\s*(\d+)\s+"
        r"(.+?)\s+:\s+(.+?)\s+"
        r"Zum Spiel",
        re.IGNORECASE,
    )

    matches = {}

    for m in pattern.finditer(text):
        date_text = m.group(2)
        time_text = m.group(3)
        competition = clean(m.group(4))
        match_id = clean(m.group(6))
        home_team = clean(m.group(7))
        away_team = clean(m.group(8))

        combined = f"{home_team} {away_team}".lower()

        if "neuhausen" not in combined:
            continue

        if "spielfrei" in combined:
            continue

        start = parse_start(date_text, time_text)

        if not (start_date <= start <= end_date):
            continue

        title = f"{home_team} vs. {away_team}"
        uid = f"{match_id}@fv-neuhausen"

        matches[uid] = {
            "title": title,
            "start": start,
            "end": start + timedelta(hours=2),
            "competition": competition,
            "uid": uid,
        }

    return matches


all_matches = {}

team_ids = get_team_ids()
print(f"{len(team_ids)} Team-IDs gefunden.")

for team_id in team_ids:
    try:
        html = fetch_matchplan(team_id)
        matches = parse_matchplan(html, team_id)
        all_matches.update(matches)
        print(f"{team_id}: {len(matches)} Spiele")
    except Exception as error:
        print(f"{team_id}: Fehler: {error}")

for item in sorted(all_matches.values(), key=lambda x: x["start"]):
    event = Event()
    event.add("summary", item["title"])
    event.add("dtstart", item["start"])
    event.add("dtend", item["end"])
    event.add("description", f"{item['competition']}\nQuelle: {CLUB_URL}")
    event.add("uid", item["uid"])
    cal.add_component(event)

with open("vereinsspielplan.ics", "wb") as file:
    file.write(cal.to_ical())

print(f"{len(all_matches)} Spiele von {DATE_FROM} bis {DATE_TO} exportiert.")
