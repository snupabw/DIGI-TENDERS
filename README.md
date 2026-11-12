# DIGI TENDERS – tender board with automatic collection

## Publish (GitHub Pages)
1. Create a repo and upload **everything in this folder** (keep the `scripts` and `.github` folders).
2. Settings → Pages → Deploy from branch → `main` / root.
3. Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save.
4. Actions tab → **Update tenders** → **Run workflow**. Open the run log to see, per source, how many open tenders were found or why it failed.
   It then runs by itself every 6 hours. (GitHub pauses scheduled runs after 60 days of no repo activity; press Run workflow to wake it.)

## How tenders get on the board
- `tenders.json` – written by the bot from the pages listed in `sources.json`. Don't edit by hand.
- `tenders-manual.json` – you add tenders by hand (edit the file on GitHub). Fields: `ref`, `t` (title), `org`, `cat` (construction/supplies/services/ict), `loc`, `d` (closing date YYYY-MM-DD), `time` (optional), `src` (link to the official notice).
- Tenders disappear automatically after their closing date.

## Add more organisations (councils, parastatals, companies)
Open `sources.json` and add the page where that organisation lists its tenders:
- `"mode": "detail"` – list page links to one page/PDF per tender. Set `link_pattern` (regex the tender links match).
- `"mode": "inline"` – list page shows "Closing Date: ..." next to each tender.
The bot obeys robots.txt. If a site forbids bots, it is skipped (the log says "blocked by robots.txt"); add those tenders to `tenders-manual.json` instead.

## Important
- The bot only publishes a tender when it finds a clearly labelled future closing date, and always links to the official notice. Tell users to verify on the notice.
- Preview locally with `python -m http.server` (opening index.html directly blocks loading the JSON files).
