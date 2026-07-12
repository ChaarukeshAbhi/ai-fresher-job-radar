"""
AI/ML Fresher Job Radar
------------------------
Pulls freshly posted AI/ML jobs suitable for FRESHERS from a mix of sources,
weighted toward startups / small & mid companies (not just MNCs), scoped to
India (incl. India-friendly remote).

Output: data/jobs.csv  (append-only, deduped by job URL)
This file is meant to be committed by a GitHub Actions workflow on a schedule,
and read into Google Sheets via:
    =IMPORTDATA("https://raw.githubusercontent.com/<you>/<repo>/main/data/jobs.csv")

Sources (all either public JSON/RSS APIs, or server-rendered pages fetched
respectfully with a normal User-Agent and low request rate):
  - RemoteOK          (public JSON API)
  - WeWorkRemotely    (public RSS)
  - Internshala       (server-rendered search results page)
  - Cutshort          (server-rendered public search page)
  - Google News RSS   (catches fresh "hiring" / "is hiring" announcements
                        from startup blogs, PR, LinkedIn mirrors, etc.)

NOTE: Site HTML structures change often. If Internshala/Cutshort parsing
breaks, open the page in a browser, inspect the job card element, and
update the CSS selectors marked with `# SELECTOR:` below.
"""

import csv
import os
import re
import time
import datetime
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH = os.path.join(DATA_DIR, "jobs.csv")

FIELDNAMES = [
    "date_found", "source", "title", "company", "location",
    "is_fresher_match", "company_size_bucket", "url", "matched_keywords",
]

# Roles/keywords that count as "AI/ML" for our purposes
AI_KEYWORDS = [
    "machine learning", "artificial intelligence", " ml engineer", " ai engineer",
    "data scientist", "nlp", "deep learning", "computer vision", "genai",
    "generative ai", "llm", "ai/ml", "ml ops", "mlops", "data science",
]

# Freshers-only signal words. A posting must match at least one.
FRESHER_KEYWORDS = [
    "fresher", "entry level", "entry-level", "0-1 year", "0 to 1 year",
    "graduate", "campus", "trainee", "junior", "associate engineer",
    "no experience required", "0-2 years",
]

# Anything explicitly senior/experienced gets dropped even if fresher words appear
EXCLUDE_KEYWORDS = [
    "senior", "sr.", "5+ years", "7+ years", "10+ years", "lead ", "principal",
    "manager", "architect", "3-5 years", "3+ years", "minimum 3 years",
]

# Known large MNCs / big-brand employers -> tagged "mnc" so you can deprioritize
# them in the sheet, NOT dropped outright (edit freely).
MNC_NAMES = [
    "tcs", "infosys", "wipro", "accenture", "cognizant", "capgemini", "hcl",
    "tech mahindra", "ibm", "google", "microsoft", "amazon", "meta", "deloitte",
    "ey", "pwc", "kpmg", "oracle", "sap", "dell", "cisco", "intel", "adobe",
    "nvidia", "goldman sachs", "jpmorgan", "morgan stanley", "sbi", "hdfc",
    "icici", "l&t", "larsen", "mahindra", "reliance", "flipkart", "swiggy",
    "zomato", "byju", "paytm",
]


def classify_company_size(company_name: str) -> str:
    name = (company_name or "").lower()
    for mnc in MNC_NAMES:
        if mnc in name:
            return "mnc"
    return "startup_or_sme"  # default assumption; unknowns treated as small/mid


def is_relevant(title: str, description: str = "") -> tuple[bool, list[str]]:
    text = f"{title} {description}".lower()
    matched = [k.strip() for k in AI_KEYWORDS if k.strip() in text]
    if not matched:
        return False, []
    if any(x in text for x in EXCLUDE_KEYWORDS):
        return False, []
    fresher_hit = any(k in text for k in FRESHER_KEYWORDS)
    return fresher_hit, matched


# ----------------------------------------------------------------------------
# Source: RemoteOK (public JSON API, no key needed)
# ----------------------------------------------------------------------------

def fetch_remoteok():
    jobs = []
    try:
        r = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[remoteok] fetch failed: {e}")
        return jobs

    for item in data:
        if not isinstance(item, dict) or "position" not in item:
            continue  # first element is metadata, skip
        title = item.get("position", "")
        description = item.get("description", "")
        company = item.get("company", "")
        location = item.get("location", "") or "Remote"
        # Keep only roles that look India-friendly remote (mention india/remote/anywhere)
        loc_text = location.lower()
        if "india" not in loc_text and "worldwide" not in loc_text and "anywhere" not in loc_text and location != "Remote":
            continue
        fresher_hit, matched = is_relevant(title, description)
        if not matched:
            continue
        jobs.append({
            "source": "RemoteOK",
            "title": title,
            "company": company,
            "location": location,
            "is_fresher_match": fresher_hit,
            "company_size_bucket": classify_company_size(company),
            "url": item.get("url", ""),
            "matched_keywords": ";".join(matched),
        })
    return jobs


# ----------------------------------------------------------------------------
# Source: WeWorkRemotely (public RSS)
# ----------------------------------------------------------------------------

def fetch_weworkremotely():
    jobs = []
    url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"[weworkremotely] fetch failed: {e}")
        return jobs

    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        title = title_el.text if title_el is not None else ""
        link = link_el.text if link_el is not None else ""
        desc = desc_el.text if desc_el is not None else ""
        fresher_hit, matched = is_relevant(title, desc)
        if not matched:
            continue
        # title format is usually "Company: Job Title"
        company = title.split(":")[0].strip() if ":" in title else ""
        jobs.append({
            "source": "WeWorkRemotely",
            "title": title,
            "company": company,
            "location": "Remote",
            "is_fresher_match": fresher_hit,
            "company_size_bucket": classify_company_size(company),
            "url": link,
            "matched_keywords": ";".join(matched),
        })
    return jobs


# ----------------------------------------------------------------------------
# Source: Internshala (server-rendered search results)
# ----------------------------------------------------------------------------

def fetch_internshala():
    jobs = []
    url = "https://internshala.com/jobs/keywords-machine%20learning,artificial%20intelligence,data%20science/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[internshala] fetch failed: {e}")
        return jobs

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[internshala] beautifulsoup4 not installed, skipping")
        return jobs

    soup = BeautifulSoup(r.text, "html.parser")
    # SELECTOR: Internshala job cards. Update this if site structure changes.
    cards = soup.select("div.individual_internship, div.job-tile, div.internship_meta")
    for card in cards:
        title_el = card.select_one("h3, .job-title-href, .heading_4_5")
        company_el = card.select_one(".company-name, .link_display_like_text")
        link_el = card.select_one("a")
        if not title_el or not link_el:
            continue
        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else "Unknown"
        href = link_el.get("href", "")
        link = href if href.startswith("http") else f"https://internshala.com{href}"
        fresher_hit, matched = is_relevant(title)
        if not matched:
            continue
        jobs.append({
            "source": "Internshala",
            "title": title,
            "company": company,
            "location": "India",
            "is_fresher_match": True,  # Internshala jobs section is early-career by default
            "company_size_bucket": classify_company_size(company),
            "url": link,
            "matched_keywords": ";".join(matched),
        })
    return jobs


# ----------------------------------------------------------------------------
# Source: Cutshort (server-rendered public search page)
# ----------------------------------------------------------------------------

def fetch_cutshort():
    jobs = []
    url = "https://cutshort.io/jobs/machine-learning-jobs"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[cutshort] fetch failed: {e}")
        return jobs

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[cutshort] beautifulsoup4 not installed, skipping")
        return jobs

    soup = BeautifulSoup(r.text, "html.parser")
    # SELECTOR: Cutshort job cards. Update this if site structure changes.
    cards = soup.select("div.job-card, li.job-listing, div[data-job-id]")
    for card in cards:
        title_el = card.select_one("h2, h3, .job-title")
        company_el = card.select_one(".company, .company-name")
        link_el = card.select_one("a")
        if not title_el or not link_el:
            continue
        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True) if company_el else "Unknown"
        href = link_el.get("href", "")
        link = href if href.startswith("http") else f"https://cutshort.io{href}"
        fresher_hit, matched = is_relevant(title)
        if not matched:
            continue
        jobs.append({
            "source": "Cutshort",
            "title": title,
            "company": company,
            "location": "India",
            "is_fresher_match": fresher_hit,
            "company_size_bucket": classify_company_size(company),
            "url": link,
            "matched_keywords": ";".join(matched),
        })
    return jobs


# ----------------------------------------------------------------------------
# Source: Google News RSS (catches "X is hiring" announcements, no key needed)
# ----------------------------------------------------------------------------

def fetch_google_news_hiring():
    jobs = []
    queries = [
        "AI ML fresher jobs hiring India startup",
        "machine learning fresher hiring India",
        "\"is hiring\" \"machine learning\" fresher India",
    ]
    for q in queries:
        url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            print(f"[google_news] fetch failed for '{q}': {e}")
            continue
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            title = title_el.text if title_el is not None else ""
            link = link_el.text if link_el is not None else ""
            fresher_hit, matched = is_relevant(title)
            if not matched:
                continue
            jobs.append({
                "source": "GoogleNews",
                "title": title,
                "company": "Unknown (check article)",
                "location": "India",
                "is_fresher_match": fresher_hit,
                "company_size_bucket": "unknown",
                "url": link,
                "matched_keywords": ";".join(matched),
            })
        time.sleep(1)
    return jobs


# ----------------------------------------------------------------------------
# CSV persistence with dedupe
# ----------------------------------------------------------------------------

def load_existing_urls():
    if not os.path.exists(CSV_PATH):
        return set()
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["url"] for row in reader if row.get("url")}


def append_jobs(jobs):
    os.makedirs(DATA_DIR, exist_ok=True)
    file_exists = os.path.exists(CSV_PATH)
    today = datetime.date.today().isoformat()

    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for j in jobs:
            writer.writerow({
                "date_found": today,
                "source": j["source"],
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "is_fresher_match": j["is_fresher_match"],
                "company_size_bucket": j["company_size_bucket"],
                "url": j["url"],
                "matched_keywords": j["matched_keywords"],
            })


def main():
    print("Fetching jobs...")
    all_jobs = []
    all_jobs += fetch_remoteok()
    all_jobs += fetch_weworkremotely()
    all_jobs += fetch_internshala()
    all_jobs += fetch_cutshort()
    all_jobs += fetch_google_news_hiring()

    print(f"Total candidates found: {len(all_jobs)}")

    existing_urls = load_existing_urls()
    new_jobs = [j for j in all_jobs if j["url"] and j["url"] not in existing_urls]

    # Rank: fresher-match + non-MNC first
    new_jobs.sort(key=lambda j: (
        not j["is_fresher_match"],
        j["company_size_bucket"] == "mnc",
    ))

    print(f"New (not seen before): {len(new_jobs)}")
    if new_jobs:
        append_jobs(new_jobs)
        print(f"Appended {len(new_jobs)} rows to {CSV_PATH}")
    else:
        print("Nothing new this run.")


if __name__ == "__main__":
    main()
