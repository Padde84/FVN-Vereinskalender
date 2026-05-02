import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event

URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I#!/section/stage"

LOCAL_TZ = tz.gettz("Europe/Berlin")

# Erstmal alle Spiele mit Neuhausen-Beteiligung.
# Später können wir wieder auf Heimspiele schärfen.
FILTER_MODE = "INVOLVED"  # INVOLVED oder HOME

now = datetime.now(LOCAL_TZ)
today = now.replace(hour=0, minute=0, second=0, microsecond=0)

end_date = datetime(now.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if now > end_date:
    end_date = datetime(now.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

headers = {
    "User-Agent": "Mozilla/5.0"
}

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Spiele")
cal.add("x-wr-timezone", "Europe/Berlin")


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def parse_date(date_str, time_str):
    dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    return dt.replace(tzinfo=LOCAL_TZ)


html = requests.get(URL, headers=headers, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

text = soup.get_text(" ", strip=True)
text = clean(text)

pattern = re.compile(
    r"(Mo|Di|Mi|Do|Fr|Sa|So),\s*"
    r"(\d{2}\.\d{2}\.\d{2})\s*\|\s*"
    r"(\d{1,2}:\d{2})\s+"
    r"(.+?)\s+"
    r"ME\s*\|\s*(\d+)\s+"
    r"(.+?)\s+:\s+(.+?)\s+"
    r"Zum Spiel",
    re.IGNORECASE
)

events = {}

for match in pattern.finditer(text):
    date_str = match.group(2)
    time_str = match.group(3)
    competition = clean(match.group(4))
    match_id = clean(match.group(5))
    home_team = clean(match.group(6))
    away_team = clean(match.group(7))

    start = parse_date(date_str, time_str)

    if not (today <= start <= end_date):
        continue

    combined = f"{home_team} {away_team}".lower()

    if FILTER_MODE == "HOME":
        if "neuhausen" not in home_team.lower():
            continue
    else:
        if "neuhausen" not in combined:
            continue

    if "spielfrei" in combined:
        continue

    title = f"{home_team} vs. {away_team}"
    uid = f"{match_id}@fv-neuhausen"

    events[uid] = {
        "title": title,
        "start": start,
        "end": start + timedelta(hours=2),
        "competition": competition,
        "uid": uid,
    }

for item in sorted(events.values(), key=lambda x: x["start"]):
    event = Event()
    event.add("summary", item["title"])
    event.add("dtstart", item["start"])
    event.add("dtend", item["end"])
    event.add("description", f"{item['competition']}\nQuelle: {URL}")
    event.add("uid", item["uid"])
    cal.add_component(event)

with open("vereinsspielplan.ics", "wb") as f:
    f.write(cal.to_ical())

print(f"{len(events)} Spiele bis {end_date.strftime('%d.%m.%Y')} exportiert.")
