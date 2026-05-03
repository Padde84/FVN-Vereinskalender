import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event

CLUB_URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I"
STAGE_URL = CLUB_URL + "#!/section/stage"

LOCAL_TZ = tz.gettz("Europe/Berlin")

now = datetime.now(LOCAL_TZ)
start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

end_date = datetime(now.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if now > end_date:
    end_date = datetime(now.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

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
    # störende FUSSBALL.DE Icon-Fonts entfernen
    text = re.sub(r"[^\w\sÄÖÜäöüß./()\-]+", " ", text)
    return clean(text)


def parse_date(date_str, time_str):
    fmt = "%d.%m.%y %H:%M" if len(date_str.split(".")[-1]) == 2 else "%d.%m.%Y %H:%M"
    return datetime.strptime(f"{date_str} {time_str}", fmt).replace(tzinfo=LOCAL_TZ)


def get_team_ids():
    html = requests.get(CLUB_URL, headers=HEADERS, timeout=30).text
    ids = sorted(set(re.findall(r"team-id/([A-Z0-9]+)", html)))
    print(f"Team-IDs gefunden: {len(ids)}")
    return ids


def fetch_urls():
    urls = []

    # 1) Vereinsspielplan direkt
    urls.append(("club-stage", STAGE_URL))

    # 2) Mannschaftsspielpläne per Ajax
    for team_id in get_team_ids():
        ajax_url = (
            "https://www.fussball.de/ajax.team.matchplan/"
            f"-/mime-type/HTML/show-venues/true/team-id/{team_id}"
            f"?datum-von={start_date.strftime('%d.%m.%Y')}"
            f"&datum-bis={end_date.strftime('%d.%m.%Y')}"
            f"&match-type=-1&wettkampftyp=-1"
        )
        urls.append((team_id, ajax_url))

    return urls


def extract_matches_from_text(text, source):
    text = clean(text)

    # Beispiel:
    # Sa, 02.05.26 | 12:15 E-Junioren | Kreisstaffel ME | 356849016 FV Spfr Neuhausen II : TSV Köngen II Zum Spiel
    pattern = re.compile(
        r"(Mo|Di|Mi|Do|Fr|Sa|So),\s*"
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
        date_str = m.group(2)
        time_str = m.group(3)
        competition = clean(m.group(4))
        match_id = clean(m.group(6))
        home_team = clean_team(m.group(7))
        away_team = clean_team(m.group(8))

        combined = f"{home_team} {away_team}".lower()

        if "neuhausen" not in combined and "wolfschlugen" not in combined:
            continue

        if "spielfrei" in combined:
            continue

        start = parse_date(date_str, time_str)

        if not (start_date <= start <= end_date):
            continue

        youth = competition.split("|")[0].strip()

        title = f"{youth} | {home_team} vs. {away_team}"

        matches[match_id] = {
            "title": title,
            "start": start,
            "end": start + timedelta(hours=2),
            "competition": competition,
            "uid": f"{match_id}@fv-neuhausen",
        }

    print(f"{source}: {len(matches)} Spiele erkannt")
    return matches


all_matches = {}

for source, url in fetch_urls():
    try:
        html = requests.get(url, headers=HEADERS, timeout=30).text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)

        matches = extract_matches_from_text(text, source)
        all_matches.update(matches)

    except Exception as e:
        print(f"{source}: Fehler: {e}")

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

print(f"FINAL: {len(all_matches)} Spiele von {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')} exportiert.")
