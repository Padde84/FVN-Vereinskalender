import re
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event
from playwright.sync_api import sync_playwright

URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I#!/section/stage"

LOCAL_TZ = tz.gettz("Europe/Berlin")

today = datetime.now(LOCAL_TZ)

end_date = datetime(today.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if today > end_date:
    end_date = datetime(today.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

from_date_str = today.strftime("%d.%m.%Y")
to_date_str = end_date.strftime("%d.%m.%Y")

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Heimspiele")
cal.add("x-wr-timezone", "Europe/Berlin")


def parse_datetime(date_str, time_str):
    if len(date_str.split(".")[-1]) == 2:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    else:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")

    return dt.replace(tzinfo=LOCAL_TZ)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    page = browser.new_page(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    page.evaluate(
        """([fromDate, toDate]) => {
            const fromInput = document.querySelector('#matchcal-date-from');
            const toInput = document.querySelector('#matchcal-date-to');

            if (fromInput) {
                fromInput.removeAttribute('readonly');
                fromInput.value = fromDate;
                fromInput.dispatchEvent(new Event('input', { bubbles: true }));
                fromInput.dispatchEvent(new Event('change', { bubbles: true }));
            }

            if (toInput) {
                toInput.removeAttribute('readonly');
                toInput.value = toDate;
                toInput.dispatchEvent(new Event('input', { bubbles: true }));
                toInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        [from_date_str, to_date_str]
    )

    print(f"Zeitraum gesetzt: {from_date_str} bis {to_date_str}")

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

    body = page.locator("body").inner_text()

    browser.close()


lines = [line.strip() for line in body.splitlines() if line.strip()]

date_pattern = re.compile(
    r"(Mo|Di|Mi|Do|Fr|Sa|So),\s*(\d{2}\.\d{2}\.\d{2,4})\s*\|\s*(\d{1,2}:\d{2})"
)

time_only_pattern = re.compile(r"^(\d{1,2}:\d{2})$")

events = []
current_date_str = None

for i, line in enumerate(lines):
    match = date_pattern.search(line)

    if match:
        current_date_str = match.group(2)
        time_str = match.group(3)
    else:
        time_match = time_only_pattern.match(line)

        if not time_match or not current_date_str:
            continue

        time_str = time_match.group(1)

    start = parse_datetime(current_date_str, time_str)

    if not (today <= start <= end_date):
        continue

    nearby = lines[i:i + 25]
    text = " ".join(nearby).lower()

    if "neuhausen" not in text:
        continue

    teams = [
        x for x in nearby
        if any(t in x for t in ["FV ", "TSV ", "SGM ", "VfB ", "FC ", "SC ", "SF "])
    ]

    if len(teams) >= 2:
        title = f"{teams[0]} vs. {teams[1]}"
    else:
        title = "FV Neuhausen Spiel"

    competition = ""
    for x in nearby:
        if any(w in x for w in ["Junioren", "Juniorinnen", "Herren", "Frauen", "Kreis", "Liga"]):
            competition = x
            break

    location = ""
    for x in nearby:
        if any(w in x for w in ["Neuhausen", "Egelsee", "Sportplatz", "Stadion"]):
            location = x
            break

    uid = f"{title}-{start.isoformat()}@fv-neuhausen"

    event = Event()
    event.add("summary", title)
    event.add("dtstart", start)
    event.add("dtend", start + timedelta(hours=2))
    event.add("location", location)
    event.add("description", f"{competition}\nQuelle: {URL}")
    event.add("uid", uid)

    events.append(event)


seen = set()

for event in events:
    uid = str(event.get("uid"))

    if uid in seen:
        continue

    seen.add(uid)
    cal.add_component(event)


with open("vereinsspielplan.ics", "wb") as f:
    f.write(cal.to_ical())


print(f"{len(seen)} Spiele bis {end_date.strftime('%d.%m.%Y')} exportiert.")
