import json
import os
import feedparser
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
from datetime import datetime, timedelta, timezone

# Lista RSS-ów
FEED_URLS = [
    "https://businessinsider.com.pl/gospodarka.feed",
    "https://businessinsider.com.pl/prawo.feed",
    "https://businessinsider.com.pl/technologie.feed",
    "https://businessinsider.com.pl/biznes.feed",
    "https://businessinsider.com.pl/nieruchomosci.feed",
    "https://businessinsider.com.pl/praca.feed",
    "https://businessinsider.com.pl/poradnik-finansowy.feed",
    "https://businessinsider.com.pl/wiadomosci.feed",
    "https://businessinsider.com.pl/polityka.feed",
    "https://businessinsider.com.pl/lifestyle.feed",
    "https://businessinsider.com.pl/sport.feed",
    "https://businessinsider.com.pl/wideo.feed",
    "https://businessinsider.com.pl/finanse.feed",
]

DAYS_TO_KEEP = 10
OUTPUT_FILE = "feed.xml"
STATE_FILE = "state.json"  # trwały magazyn

def extract_category(url: str) -> str:
    return url.split("com.pl/")[1].split(".feed")[0]

def parse_date(entry):
    # feedparser daje published_parsed jako time.struct_time (UTC-like), ale bywa różnie w feedach.
    # Trzymamy wszystko w UTC.
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return None

def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {}  # guid -> item
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # oczekujemy dict guid->item
        return data if isinstance(data, dict) else {}
    except Exception:
        # Jak plik się wysypie, lepiej zacząć od zera niż przerwać publikacje
        return {}

def save_state_atomic(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)

def pubdate_rfc822(dt: datetime) -> str:
    # RSS lubi RFC822; trzymamy GMT
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

def pubdate_dt_from_rfc822(s: str):
    # czytamy to, co sami zapisujemy: "Mon, 17 Feb 2026 08:15:00 GMT"
    # Uwaga: %a/%b zależą od locale, ale w praktyce tu jest angielski format.
    try:
        dt = datetime.strptime(s, "%a, %d %b %Y %H:%M:%S GMT")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=DAYS_TO_KEEP)

# 1) Wczytaj stan (archiwum GUID->item)
state = load_state(STATE_FILE)

# 2) Pobierz nowe wpisy i dopisz/odśwież w stanie
new_count = 0
updated_count = 0

for url in FEED_URLS:
    category = extract_category(url)
    parsed = feedparser.parse(url)

    for entry in parsed.entries:
        guid = entry.get("guid", entry.get("id", "")) or ""
        pubdt = parse_date(entry)
        if not guid or not pubdt:
            continue

        # UWAGA: tu świadomie NIE filtrujemy po cutoff na etapie pobierania,
        # bo jeśli źródłowy RSS przestanie pokazywać wpis, a my mamy go w stanie,
        # to i tak utrzymamy go aż do cutoff. Natomiast wpisy bardzo stare z RSS
        # i tak wyczyścimy w kroku 3.
        enclosure_url = ""
        enclosure_type = "image/jpeg"
        for link in entry.get("links", []):
            if link.get("rel") == "enclosure":
                enclosure_url = link.get("href", "")
                enclosure_type = link.get("type", "image/jpeg")
                break

        item = {
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "description": entry.get("description", ""),
            "guid": guid,
            "pubDate": pubdate_rfc822(pubdt),
            "enclosure": enclosure_url,
            "enclosure_type": enclosure_type,
            "category": category,
        }

        if guid in state:
            # Odświeżamy dane (np. zmiana tytułu/opisu/miniatury), ale pubDate zostaje z entry.
            state[guid] = item
            updated_count += 1
        else:
            state[guid] = item
            new_count += 1

# 3) Przytnij stan do ostatnich N dni (gwarantowana retencja niezależnie od RSS źródłowego)
before_prune = len(state)
to_delete = []

for guid, item in state.items():
    dt = pubdate_dt_from_rfc822(item.get("pubDate", ""))
    if not dt or dt < cutoff:
        to_delete.append(guid)

for guid in to_delete:
    del state[guid]

after_prune = len(state)
pruned = before_prune - after_prune

# 4) Wygeneruj XML z tego, co jest w stanie
items = list(state.values())
# sortujemy po realnym datetime, nie po stringu
def item_dt(it):
    dt = pubdate_dt_from_rfc822(it.get("pubDate", ""))
    return dt or datetime(1970, 1, 1, tzinfo=timezone.utc)

items.sort(key=item_dt, reverse=True)

rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "Business Insider Polska - Agregowany Feed"
ET.SubElement(channel, "link").text = "https://businessinsider.com.pl/"
ET.SubElement(channel, "description").text = "Zbiorczy RSS Business Insider Polska"

for item in items:
    item_el = ET.SubElement(channel, "item")
    ET.SubElement(item_el, "title").text = item.get("title", "")
    ET.SubElement(item_el, "link").text = item.get("link", "")
    ET.SubElement(item_el, "description").text = item.get("description", "")
    ET.SubElement(item_el, "guid", isPermaLink="false").text = item.get("guid", "")
    ET.SubElement(item_el, "pubDate").text = item.get("pubDate", "")
    ET.SubElement(item_el, "category").text = item.get("category", "")

    if item.get("enclosure"):
        ET.SubElement(
            item_el,
            "enclosure",
            url=item.get("enclosure", ""),
            type=item.get("enclosure_type", "image/jpeg"),
            length="0",
        )

rough_string = ET.tostring(rss, encoding="utf-8")
reparsed = minidom.parseString(rough_string)
pretty_xml = reparsed.toprettyxml(encoding="UTF-8")

with open(OUTPUT_FILE, "wb") as f:
    f.write(pretty_xml)

# 5) Zapisz stan na dysk (atomowo)
save_state_atomic(STATE_FILE, state)

print(
    f"Nowe: {new_count}, zaktualizowane: {updated_count}, "
    f"przycięte (>{DAYS_TO_KEEP} dni): {pruned}. "
    f"Finalnie w feedzie: {len(items)}. Zapisano do {OUTPUT_FILE}."
)
