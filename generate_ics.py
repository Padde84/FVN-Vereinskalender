import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event

CLUB_URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I"
SEASON = "2526"
LOCAL_TZ = tz.gettz("Europe/Berlin")

ONLY_NEUHAUSEN_HOME_OR_VENUE = True

today = datetime.now(LOCAL_TZ)
end_date = datetime(today.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if today > end_date:
    end_date = datetime(today.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

from_date = today.strftime("%d.%m.%Y")
to_date = end_date.strftime("%d.%m.%Y")

headers = {"User-Agent": "Mozilla/5.0"}

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Heimspiele")
cal.add("x-wr-timezone", "Europe/Berlin")


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get_team_ids():
    html = requests.get(CLUB_URL, headers=headers, timeout=30).text
    ids = sorted(set(re.findall(r"team-id/([A-Z0-9]+)", html)))
    return ids


def parse_date(date_text):
    match = re.search(r"(\d{2}\.\d{2}\.\d{2,4}).*?(\d{1,2}:\d{2})", date_text)
    if not match:
        return None

    date_str, time_str = match.groups()

    fmt = "%d.%m.%y %H:%M" if len(date_str.split(".")[-1]) == 2 else "%d.%m.%Y %H:%M"
    return datetime.strptime(f"{date_str} {time_str}", fmt).replace(tzinfo=LOCAL_TZ)


def fetch_team_matchplan(team_id):
    url = f"https://www.fussball.de/ajax.team.matchplan/-/mime-type/HTML/show-venues/true/team-id/{team_id}"

    params = {
        "datum-von": from_date,
        "datum-bis": to_date,
    }

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.text


def parse_matches(html, team_id):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr")

    matches = []

    for idx, row in enumerate(rows):
        row_text = clean(row.get_text(" "))

        if not re.search(r"\d{1,2}:\d{2}", row_text):
            continue

        start = parse_date(row_text)
        if not start:
            continue

        if not (today <= start <= end_date):
            continue

        block_rows = rows[idx:idx + 4]
        block_text = clean(" ".join(r.get_text(" ") for r in block_rows))

        team_names = [clean(x.get_text(" ")) for x in block_rows[1].select(".club-name")]
        team_names = [x for x in team_names if x]

        if len(team_names) >= 2:
            home_team = team_names[0]
            away_team = team_names[1]
        else:
            parts = re.split(r"\s+:\s+", block_text)
            if len(parts) < 2:
                continue
            home_team = clean(parts[0].split("|")[-1])
            away_team = clean(parts[1].split("Zum Spiel")[0])

        venue = ""
        venue_match = re.search(r"(Sportplatz|Stadion|Egelsee|Neuhausen|73765)[^|]*", block_text, re.I)
        if venue_match:
            venue = clean(venue_match.group(0))

        combined = f"{home_team} {away_team} {venue}".lower()

        if ONLY_NEUHAUSEN_HOME_OR_VENUE:
            is_home_team = "neuhausen" in home_team.lower()
            is_neuhausen_venue = any(x in combined for x in ["egelsee", "73765", "neuhausen auf den fildern"])
            if not (is_home_team or is_neuhausen_venue):
                continue

        competition = ""
        comp_match = re.search(r"(Herren|A-Junioren|B-Junioren|C-Junioren|D-Junioren|E-Junioren|F-Junioren|G-Junioren).*?(Kreisstaffel|Kreisliga|Landesliga|Bezirksliga|Leistungsstaffel|Freundschaftsspiele|Pokal)?", block_text)
        if comp_match:
            competition = clean(comp_match.group(0))

        title = f"{home_team} vs. {away_team}"

        matches.append({
            "title": title,
            "start": start,
            "end": start + timedelta(hours=2),
            "competition": competition,
            "location": venue,
            "uid": f"{team_id}-{title}-{start.isoformat()}@fv-neuhausen",
        })

    return matches


all_events = {}

team_ids = get_team_ids()
print(f"{len(team_ids)} Team-IDs gefunden.")

 for_count = 0

for team_id in team_ids:
    try:
        html = fetch_team_matchplan(team_id)
        matches = parse_matches(html, team_id)

        for match in matches:
            all_events[match["uid"]] = match

        print(f"{team_id}: {len(matches)} Spiele")
    except Exception as e:
        print(f"{team_id}: Fehler: {e}")

for item in all_events.values():
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

print(f"{len(all_events)} Spiele bis {end_date.strftime('%d.%m.%Y')} exportiert.")
