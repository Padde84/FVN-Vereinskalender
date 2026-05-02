import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
from datetime import datetime, timedelta
from dateutil import tz
import re

URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I#!/"

ONLY_NEUHAUSEN = True
END_DATE_MONTH = 6
END_DATE_DAY = 30

LOCAL_TZ = tz.gettz("Europe/Berlin")

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen Vereinsspielplan//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Vereinsspielplan")
cal.add("x-wr-timezone", "Europe/Berlin")

today = datetime.now(LOCAL_TZ)

# Saison-Ende: immer bis 30.06.
end_date = datetime(
    today.year,
    END_DATE_MONTH,
    END_DATE_DAY,
    23,
    59,
    tzinfo=LOCAL_TZ
)

# Falls wir nach dem 30.06. sind, nimm den 30.06. des Folgejahres
if today > end_date:
    end_date = datetime(
        today.year + 1,
        END_DATE_MONTH,
        END_DATE_DAY,
        23,
        59,
        tzinfo=LOCAL_TZ
    )

headers = {
    "User-Agent": "Mozilla/5.0"
}

html = requests.get(URL, headers=headers, timeout=30).text
soup = BeautifulSoup(html, "html.parser")

text = soup.get_text("\n", strip=True)
lines = [line.strip() for line in text.split("\n") if line.strip()]

events = []

date_pattern = re.compile(
    r"(Mo|Di|Mi|Do|Fr|Sa|So),\s*(\d{2}\.\d{2}\.\d{4}|\d{2}\.\d{2}\.\d{2})\s*\|\s*(\d{1,2}:\d{2})"
)

for i, line in enumerate(lines):
    match = date_pattern.search(line)
    if not match:
        continue

    date_str = match.group(2)
    time_str = match.group(3)

    if len(date_str.split(".")[-1]) == 2:
        dt = datetime.strptime(
            date_str + " " + time_str,
            "%d.%m.%y %H:%M"
        )
    else:
        dt = datetime.strptime(
            date_str + " " + time_str,
            "%d.%m.%Y %H:%M"
        )

    dt = dt.replace(tzinfo=LOCAL_TZ)

    # Nur zukünftige Termine bis 30.06.
    if not (today <= dt <= end_date):
        continue

    nearby = lines[i:i + 15]
    nearby_text = " ".join(nearby).lower()

    # Nur Spiele mit Bezug / Spielort Neuhausen
    if ONLY_NEUHAUSEN:
        neuhausen_keywords = [
            "neuhausen",
            "fv spfr neuhausen",
            "sportfreunde neuhausen",
            "stadion neuhausen",
            "sportplatz neuhausen",
            "egelsee",
            "fvn"
        ]

        if not any(keyword in nearby_text for keyword in neuhausen_keywords):
            continue

    title = "Fußballspiel FV Neuhausen"

    teams = [
        x for x in nearby
        if (
            "FV" in x
            or "SGM" in x
            or "TSV" in x
            or "VfB" in x
            or "SF" in x
            or "FC" in x
            or "SC" in x
        )
    ]

    if len(teams) >= 2:
        title = f"{teams[0]} vs. {teams[1]}"

    competition = next(
        (
            x for x in nearby
            if (
                "Junioren" in x
                or "Juniorinnen" in x
                or "Herren" in x
                or "Frauen" in x
                or "Kreisstaffel" in x
                or "Kreisliga" in x
                or "Bezirksliga" in x
            )
        ),
        ""
    )

    events.append({
        "title": title,
        "start": dt,
        "competition": competition,
        "url": URL
    })

for item in events:
    event = Event()
    event.add("summary", item["title"])
    event.add("dtstart", item["start"])
    event.add("dtend", item["start"] + timedelta(hours=2))
    event.add(
        "description",
        f"{item['competition']}\nQuelle: {item['url']}"
    )
    event.add(
        "uid",
        f"{item['title']}-{item['start'].isoformat()}@fv-neuhausen"
    )

    cal.add_component(event)

with open("vereinsspielplan.ics", "wb") as f:
    f.write(cal.to_ical())

print(f"{len(events)} Spiele bis {end_date.strftime('%d.%m.%Y')} exportiert.")
