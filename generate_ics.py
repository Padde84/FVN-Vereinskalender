import re
from datetime import datetime, timedelta
from dateutil import tz
from icalendar import Calendar, Event
from playwright.sync_api import sync_playwright

URL = "https://www.fussball.de/verein/fv-spfr-neuhausen-wuerttemberg/-/id/00ES8GNAVO0000ALVV0AG08LVUPGND5I#!/section/stage"

LOCAL_TZ = tz.gettz("Europe/Berlin")

today = datetime.now(LOCAL_TZ)

# immer bis 30.06.
end_date = datetime(today.year, 6, 30, 23, 59, tzinfo=LOCAL_TZ)
if today > end_date:
    end_date = datetime(today.year + 1, 6, 30, 23, 59, tzinfo=LOCAL_TZ)

from_date_str = today.strftime("%d.%m.%Y")
to_date_str = end_date.strftime("%d.%m.%Y")

cal = Calendar()
cal.add("prodid", "-//FV Neuhausen//DE")
cal.add("version", "2.0")
cal.add("x-wr-calname", "FV Neuhausen Heimspiele")

def parse_datetime(date_str, time_str):
    if len(date_str.split(".")[-1]) == 2:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M")
    else:
        dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
    return dt.replace(tzinfo=LOCAL_TZ)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto(URL, timeout=60000)
    page.wait_for_timeout(5000)

    # Datum per JS setzen (wichtig!)
    page.evaluate(
        """([fromDate, toDate]) => {
            const fromInput = document.querySelector('#matchcal-date-from');
            const toInput = document.querySelector('#matchcal-date-to');

            if (fromInput) {
                fromInput.removeAttribute('readonly');
                fromInput.value = fromDate;
                fromInput.dispatchEvent(new Event('change', { bubbles: true }));
            }

            if (toInput) {
                toInput.removeAttribute('readonly');
                toInput.value = toDate;
                toInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""",
        [from_date_str, to_date_str]
    )

    # Spielstätten anzeigen
    try:
        page.get_by_text("Spielstätten anzeigen").click()
    except:
        pass

    # LOS klicken
    try:
        page.get_by_text("LOS").click()
    except:
        pass

    page.wait_for_timeout(8000)

    body = page.locator("body").inner_text()
    browser.close()

lines = [l.strip() for l in body.splitlines() if l.strip()]

date_pattern = re.compile(
    r"(Mo|Di|Mi|Do|Fr|Sa|So),\s*(\d{2}\.\d{2}\.\d{2,4})\s*\|\s*(\d{1,2}:\d{2})"
)

events = []

for i, line in enumerate(lines):
    match = date_pattern.search(line)
    if not match:
        continue

    date_str = match.group(2)
    time_str = match.group(3)

    start = parse_datetime(date_str, time_str)

    if not (today <= start <= end_date):
        continue

    nearby = lines[i:i + 20]
    text = " ".join(nearby).lower()

    # nur Neuhausen-Spiele
    if "neuhausen" not in text:
        continue

    teams = [x for x in nearby if any(t in x for t in ["FV", "TSV", "SGM", "VfB", "FC"])]

    if len(teams) >= 2:
        title = f"{teams[0]} vs. {teams[1]}"
    else:
        title = "FV Neuhausen Spiel"

    uid = f"{title}-{start.isoformat()}"

    event = Event()
    event.add("summary", title)
    event.add("dtstart", start)
    event.add("dtend", start + timedelta(hours=2))
    event.add("description", URL)
    event.add("uid", uid)

    cal.add_component(event)

with open("vereinsspielplan.ics", "wb") as f:
    f.write(cal.to_ical())

print("ICS erfolgreich erstellt!")
