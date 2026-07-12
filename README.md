# AI/ML Fresher Job Radar

Automatically finds newly posted **AI/ML jobs for freshers** in India, weighted
toward startups and small/mid companies rather than MNCs, and appends them to
`data/jobs.csv` once a day — no laptop required, runs entirely on GitHub Actions.

## 1. One-time setup (10 minutes)

1. Create a **new GitHub repo** (public or private, your choice — public is
   simpler since Google Sheets can read the raw file directly without a token).
2. Upload these files keeping the folder structure:
   ```
   job_scraper.py
   requirements.txt
   .github/workflows/daily_job_search.yml
   ```
3. Go to your repo → **Settings → Actions → General → Workflow permissions**
   → select **"Read and write permissions"**. (This lets the workflow commit
   the updated CSV back to the repo.)
4. Go to the **Actions** tab → you'll see "Daily AI/ML Fresher Job Search" →
   click **Run workflow** once to test it manually.
5. After it runs, check `data/jobs.csv` in your repo — it should have rows.

From then on, it runs automatically every day at ~9:00 AM IST.

## 2. Pull it into Google Sheets (no API key needed)

1. Open your repo, go to `data/jobs.csv`, click **Raw**, copy that URL.
   It looks like:
   `https://raw.githubusercontent.com/<your-username>/<repo>/main/data/jobs.csv`
2. In a Google Sheet, in cell A1, type:
   ```
   =IMPORTDATA("https://raw.githubusercontent.com/<your-username>/<repo>/main/data/jobs.csv")
   ```
3. Google Sheets refreshes `IMPORTDATA` automatically every couple of hours,
   or manually via **File → Settings → Recalculation**, or just reopening the
   sheet. Since the workflow only *appends* new rows, your CSV — and the
   sheet — grows a little each day.

## 3. How it decides what's relevant

- **AI/ML match**: title/description must contain a keyword like "machine
  learning", "data scientist", "computer vision", "GenAI", "LLM", etc.
- **Fresher match**: flagged `True` if it also contains fresher-signal words
  ("fresher", "entry level", "graduate", "trainee", "0-1 year", etc.).
  Postings clearly senior ("5+ years", "lead", "manager") are dropped outright.
- **Company size bucket**: `mnc` if the company name matches a hardcoded list
  of large/brand-name employers (TCS, Infosys, Google, Amazon, etc. — edit
  `MNC_NAMES` in `job_scraper.py` to adjust), otherwise `startup_or_sme`.
  Results are sorted so fresher-matched, non-MNC postings show up first in
  the CSV — nothing is deleted, just reordered, so you can still see MNC
  options if you want them.

## 4. Sources included, and why

| Source | Type | Why |
|---|---|---|
| RemoteOK | Public JSON API | Reliable, no scraping fragility |
| WeWorkRemotely | Public RSS | Reliable, catches remote-friendly roles |
| Internshala | Server-rendered page | India's largest fresher/internship board |
| Cutshort | Server-rendered page | India-focused, startup-heavy job board |
| Google News RSS | Public RSS, no key | Catches "X is hiring" announcements from startup blogs/PR that don't show up on job boards yet |

**Not included on purpose:** LinkedIn and Naukri. Both are JS-heavy and their
Terms of Service explicitly prohibit automated scraping — doing so risks your
account/IP getting flagged. If you want them later, the safer path is
LinkedIn's official Jobs API (requires partner access) or a paid, ToS-compliant
aggregator API like SerpAPI's Google Jobs endpoint.

## 5. Extending it

- **Add more sources**: write a new `fetch_xxx()` function returning a list of
  dicts with the same keys as the others, then add it to `main()`.
- **Tighten/loosen the fresher filter**: edit `FRESHER_KEYWORDS` and
  `EXCLUDE_KEYWORDS` near the top of `job_scraper.py`.
- **Selectors breaking**: Internshala/Cutshort occasionally change their HTML.
  If their section of the CSV goes empty, open the job search page in a
  browser, right-click a job card → Inspect, and update the CSS selectors
  marked `# SELECTOR:` in `job_scraper.py`.
- **Telegram/email alerts later**: easy to bolt on — a few lines using the
  Telegram Bot API or `smtplib` inside `main()` right after `new_jobs` is
  computed, if you decide you want a push notification instead of just the
  sheet.

## 6. A note on realistic expectations

Scraper-based tools like this are a **supplement**, not a replacement, for
actively applying. Site structures change, some sources will occasionally
return nothing, and startup postings move fast — treat the sheet as a daily
shortlist to triage in 5–10 minutes, not a fire-and-forget system.
