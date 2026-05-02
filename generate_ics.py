import re
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event
from playwright.sync_api import sync_playwright

URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I#!/section/stage"

LOCAL_TZ = tz.gettz("Europe/Berlin")
ONLY_NEUHAUSEN_SPIELORT = True

today = datetime.now(LOCAL_TZ)

end_date = datetime(today.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if today > end_date:
    end_date = datetime(today.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

from_date_str = today.strftime("%d.%m.%Y")
to_date_str = end_date.strftime("%d.%m.%Y")

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen Vereinsspielplan//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Heimspiele")
cal.add("x-wr-timezone", "Europe/Berlin")

def parse_datetime(date_str, time_str):
    if len(date_str.split(".")[-1]) == 2:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    else:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
    return dt.replace(tzinfo=LOCAL_TZ)

def clean_line(line):
    return re.sub(r"\s+", " ", line).strip()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)

    print("Vereinsspielplan-Seite geladen.")
    page.wait_for_timeout(5000)

    # Datumsfelder setzen
    date_inputs = page.locator("input").all()
    found_date_inputs = []

    for inp in date_inputs:
        try:
            value = inp.input_value()
            if re.match(r"\d{2}\.\d{2}\.\d{4}", value):
                found_date_inputs.append(inp)
        except Exception:
            pass

    if len(found_date_inputs) >= 2:
        found_date_inputs[0].fill(from_date_str)
        found_date_inputs[1].fill(to_date_str)
        print(f"Zeitraum gesetzt: {from_date_str} bis {to_date_str}")
    else:
        print("Datumsfelder nicht gefunden.")

    try:
        page.get_by_text("Spielstätten anzeigen", exact=True).click(timeout=5000)
        print("Spielstätten anzeigen aktiviert.")
    except Exception:
        print("Spielstätten anzeigen konnte nicht aktiviert werden.")

    try:
        page.get_by_text("LOS", exact=True).click(timeout=5000)
        print("LOS geklickt.")
    except Exception:
        print("LOS-Button wurde nicht gefunden.")

    page.wait_for_timeout(8000)

    body_text = page.locator("body").inner_text()

    browser.close()

lines = [clean_line(x) for x in body_text.splitlines() if clean_line(x)]

events = []

date_line_pattern = re.compile(
    r"(Mo|Di|Mi|Do|Fr|Sa|So),\s*(\d{2}\.\d{2}\.\d{2,4})\s*\|\s*(\d{1,2}:\d{2})"
)

for i, line in enumerate(lines):
    match = date_line_pattern.search(line)
    if not match:
        continue

    date_str = match.group(2)
    time_str = match.group(3)
    start_dt = parse_datetime(date_str, time_str)

    if not (today <= start_dt <= end_date):
        continue

    nearby = lines[i:i + 25]
    nearby_text = " ".join(nearby).lower()

    if ONLY_NEUHAUSEN_SPIELORT:
        if "neuhausen" not in nearby_text:
            continue

    teams = [
        x for x in nearby
        if any(token in x for token in ["FV ", "SGM ", "TSV ", "VfB ", "SF ", "FC ", "SC "])
    ]

    if len(teams) >= 2:
        title = f"{teams[0]} vs. {teams[1]}"
    else:
        title = "Fußballspiel FV Neuhausen"

    competition = next(
        (
            x for x in nearby
            if any(word in x for word in [
                "Junioren",
                "Juniorinnen",
                "Herren",
                "Frauen",
                "Kreisstaffel",
                "Kreisliga",
                "Bezirksliga"
            ])
        ),
        ""
    )

    location = ""
    for x in nearby:
        if "Neuhausen" in x or "Egelsee" in x or "Sportplatz" in x:
            location = x
            break

    uid = f"{title}-{start_dt.isoformat()}@fv-neuhausen"

    events.append({
        "title": title,
        "start": start_dt,
        "end": start_dt + timedelta(hours=2),
        "competition": competition,
        "location": location,
        "uid": uid
    })

# Duplikate entfernen
unique_events = {}
for event in events:
    unique_events[event["uid"]] = event

for item in unique_events.values():
    event = Event()
    event.add("summary", item["title"])
    event.add("dtstart", item["start"])
    event.add("dtend", item["end"])
    event.add("location", item["location"])
    event.add("description", f"{item['competition']}\nQuelle: {URL}")
    event.add("uid", item["uid"])
    cal.add_component(event)

with open("vereinsspielplan.ics", "wb") as f:
    f.write(cal.to_ical())

print(f"{len(unique_events)} Spiele bis {end_date.strftime('%d.%m.%Y')} exportiert.")
