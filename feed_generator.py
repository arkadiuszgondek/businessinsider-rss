import feedparser
from datetime import datetime, timedelta
from hashlib import md5
import xml.etree.ElementTree as ET

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
]

DAYS_TO_KEEP = 7
OUTPUT_FILE = "feed.xml"

# Pomocnicze
def extract_category(url):
    return url.split("com.pl/")[1].split(".feed")[0]
from datetime import timezone

def parse_date(entry):
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return None

# Zbiór unikalnych guidów
seen_guids = set()
items = []

# Data graniczna
from datetime import timezone
now = datetime.now(timezone.utc)
cutoff = now - timedelta(days=DAYS_TO_KEEP)

# Pobieranie i przetwarzanie
for url in FEED_URLS:
    category = extract_category(url)
    parsed = feedparser.parse(url)

    for entry in parsed.entries:
        guid = entry.get("guid", entry.get("id", ""))
        pubdate = parse_date(entry)

        if not guid or guid in seen_guids:
            continue
        if not pubdate or pubdate < cutoff:
            continue

        seen_guids.add(guid)

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
            "pubDate": pubdate.strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "enclosure": enclosure_url,
            "enclosure_type": enclosure_type,
            "category": category,
        }

        items.append(item)

# Sortowanie od najnowszych
items.sort(key=lambda x: x["pubDate"], reverse=True)

# Generowanie XML
rss = ET.Element("rss", version="2.0")
channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = "Business Insider Polska - Agregowany Feed"
ET.SubElement(channel, "link").text = "https://businessinsider.com.pl/"
ET.SubElement(channel, "description").text = "Zbiorczy RSS Business Insider Polska"

for item in items:
    item_el = ET.SubElement(channel, "item")
    ET.SubElement(item_el, "title").text = item["title"]
    ET.SubElement(item_el, "link").text = item["link"]
    ET.SubElement(item_el, "description").text = item["description"]
    ET.SubElement(item_el, "guid", isPermaLink="false").text = item["guid"]
    ET.SubElement(item_el, "pubDate").text = item["pubDate"]
    ET.SubElement(item_el, "category").text = item["category"]

    if item["enclosure"]:
        ET.SubElement(item_el, "enclosure", url=item["enclosure"], type=item["enclosure_type"], length="0")

# Zapis do pliku
import xml.dom.minidom as minidom

rough_string = ET.tostring(rss, encoding="utf-8")
reparsed = minidom.parseString(rough_string)
pretty_xml = reparsed.toprettyxml(encoding="UTF-8")

with open(OUTPUT_FILE, "wb") as f:
    f.write(pretty_xml)

print(f"Zapisano {len(items)} artykułów do {OUTPUT_FILE}")
