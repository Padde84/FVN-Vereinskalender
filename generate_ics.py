import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event

CLUB_URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I"
LOCAL_TZ = tz.gettz("Europe/Berlin")

MATCH_TYPE = -1

now = datetime.now(LOCAL_TZ)
start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

end_date = datetime(now.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if now > end_date:
    end_date = datetime(now.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

DATE_FROM = start_date.strftime("%d.%m.%Y")
DATE_TO = end_date.strftime("%d.%m.%Y")

HEADERS = {
    "User-Agent": "Mozilla/5.0",
}

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Spiele")
cal.add("x-wr-timezone", "Europe/Berlin")


def clean(text):
    text = text or ""
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def clean_team(text):
    text = clean(text)
    text = re.sub(r"[^\w\sÄÖÜäöüß./()\-]+", " ", text)
    return clean(text)


def normalize_team_name(name):
    name = clean_team(name)

    name = name.replace("FV Spfr Neuhausen", "FV Neuhausen")

    name = re.sub(r"\bIV\b", "4", name)
    name = re.sub(r"\bIII\b", "3", name)
    name = re.sub(r"\bII\b", "2", name)
    name = re.sub(r"\bI\b", "1", name)

    return clean(name)


def get_youth_from_match_id(match_id, league):
    prefix_map = {
        "351619": "E-Junioren",
        "356849": "E-Junioren",
        "356850": "E-Junioren",

        "356592": "D-Junioren",

        "352265": "C-Junioren",
        "352406": "C-Junioren",

        "352386": "B-Junioren",
        "352010": "A-Junioren",

        "352621": "F-Junioren",

        "355923": "Herren",
        "356082": "Herren",
    }

    for prefix, youth in prefix_map.items():
        if str(match_id).startswith(prefix):
            return youth

    if "Landesliga" in league or "Kreisliga" in league:
        return "Herren"

    return ""


def get_team_ids():
    html = requests.get(CLUB_URL, headers=HEADERS, timeout=30).text
    ids = sorted(set(re.findall(r"team-id/([A-Z0-9]+)", html)))
    print(f"{len(ids)} Team-IDs gefunden")
    return ids


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

    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.text


def parse_start(date_text, time_text):
    fmt = "%d.%m.%y %H:%M" if len(date_text.split(".")[-1]) == 2 else "%d.%m.%Y %H:%M"
    return datetime.strptime(f"{date_text} {time_text}", fmt).replace(tzinfo=LOCAL_TZ)


def parse_matchplan(html):
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" ", strip=True))

    pattern = re.compile(
        r"(?:(Mo|Di|Mi|Do|Fr|Sa|So),\s*)?"
        r"(\d{2}\.\d{2}\.\d{2,4})\s*\|\s*"
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
        league = clean(m.group(4))
        match_id = clean(m.group(6))
        home_team = clean_team(m.group(7))
        away_team = clean_team(m.group(8))

        combined = f"{home_team} {away_team}".lower()

        if "neuhausen" not in combined:
            continue

        if "spielfrei" in combined:
            continue

        start = parse_start(date_text, time_text)

        if not (start_date <= start <= end_date):
            continue

        home_team_short = normalize_team_name(home_team)
        away_team_short = normalize_team_name(away_team)

        youth = get_youth_from_match_id(match_id, league)

        if youth:
            title = f"{youth} {home_team_short} - {away_team_short}"
        else:
            title = f"{home_team_short} - {away_team_short}"

        uid = f"{match_id}@fv-neuhausen"

        matches[uid] = {
            "title": title,
            "start": start,
            "end": start + timedelta(hours=2),
            "description": league,
            "uid": uid,
        }

    return matches


all_matches = {}

team_ids = get_team_ids()

for team_id in team_ids:
    try:
        html = fetch_matchplan(team_id)
        matches = parse_matchplan(html)
        all_matches.update(matches)
        print(f"{team_id}: {len(matches)} Spiele")
    except Exception as e:
        print(f"{team_id}: Fehler: {e}")

for item in sorted(all_matches.values(), key=lambda x: x["start"]):
    event = Event()
    event.add("summary", item["title"])
    event.add("dtstart", item["start"])
    event.add("dtend", item["end"])
    event.add("description", f"{item['description']}\nQuelle: {CLUB_URL}")
    event.add("uid", item["uid"])
    cal.add_component(event)

with open("vereinsspielplan.ics", "wb") as f:
    f.write(cal.to_ical())

print(f"{len(all_matches)} Spiele bis {end_date.strftime('%d.%m.%Y')} exportiert.")
