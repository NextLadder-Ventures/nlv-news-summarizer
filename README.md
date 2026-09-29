# News Summarizer Slack Bot

A Slack bot that monitors a channel for posted links, fetches the article content, and replies in-thread with an AI-generated summary using Claude.

## How it works

1. Someone posts a link in your Slack channel (e.g. `#news-you-can-use`)
2. The bot detects the URL, fetches the article, and extracts the text
3. Claude summarizes the article into a TL;DR, key points, and a "why it matters" line
4. The bot replies in-thread so the channel stays clean

The bot uses **Socket Mode**, which means it connects outbound to Slack via WebSocket — no public URL or ingress needed. This makes deployment simple on any platform.

### What the bot does and doesn't summarize

- **Top-level messages only.** The bot only summarizes links posted as new top-level messages in the channel. Links added in a thread reply (e.g. when people discuss the original post and drop additional links) are ignored, so the bot doesn't summarize tangential links from the back-and-forth.
- **One summary per unique link.** If the same link appears more than once in a single message — for example, a hyperlinked label *and* the raw URL pasted alongside it — the bot summarizes it only once. Duplicate detection ignores trailing slashes and tracking parameters (`utm_*`, `fbclid`, `gclid`), so `example.com/a` and `example.com/a/?utm_source=slack` count as the same article.

## Prerequisites

- Python 3.11+
- A Slack workspace where you can create apps
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

### 1. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** > **From scratch**
2. Name it something like `News Summarizer` and select your workspace

#### Enable Socket Mode

3. Go to **Settings > Socket Mode** (left sidebar) and toggle **Enable Socket Mode** on
4. Go to **Settings > Basic Information > App-Level Tokens**
5. Click **Generate Token and Scopes**, name it `socket-token`, and add the scope `connections:write`
6. Copy the token (starts with `xapp-`) — this is your `SLACK_APP_TOKEN`

#### Set Bot Permissions

7. Go to **Features > OAuth & Permissions > Scopes > Bot Token Scopes** and add:
   - `channels:history` — read messages in public channels
   - `channels:read` — view basic channel info
   - `chat:write` — post messages
   - `groups:history` — read messages in private channels (optional, if the channel is private)

#### Enable Events

> **Important:** Socket Mode must be enabled (step 3) *before* this step, otherwise Slack will require a Request URL and won't let you save.

8. Go to **Features > Event Subscriptions** and toggle **Enable Events** on
9. Under **Subscribe to bot events**, add:
   - `message.channels` — listens for messages in public channels
   - `message.groups` — (optional) listens in private channels
   - `app_mention` — responds when @mentioned
10. Click **Save Changes**

#### Install the App

10. Go to **Settings > Install App** and click **Install to Workspace**
11. Copy the **Bot User OAuth Token** (starts with `xoxb-`) — this is your `SLACK_BOT_TOKEN`

#### Invite the Bot to Your Channel

12. In Slack, go to `#news-you-can-use` (or whichever channel) and type:
    ```
    /invite @News Summarizer
    ```

### 2. Configure Environment Variables

Copy the example env file and fill in your tokens:

```bash
cp .env.example .env
```

Edit `.env`:

```
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-level-token
ANTHROPIC_API_KEY=sk-ant-your-api-key
```

### 3. Run Locally

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Start the bot
python -m bot.app
```

You should see `Starting News Summarizer Bot...` in the console. Post a news link in your channel to test it.

## Deploying to Railway

[Railway](https://railway.app) is the easiest way to keep this bot running 24/7. The free tier includes $5/month in credits, which is more than enough for this bot.

### First-time setup

1. Create an account at [railway.app](https://railway.app)
2. Install the [Railway GitHub App](https://github.com/apps/railway-app) on your GitHub account — grant it access to this repository (or all repositories)
3. Back in Railway, click **New Project** > **Deploy from GitHub Repo**
4. Select this repository — Railway will auto-detect the Dockerfile and deploy

### Set environment variables

5. In your Railway project, go to **Variables** and add:
   - `SLACK_BOT_TOKEN` = your `xoxb-...` token
   - `SLACK_APP_TOKEN` = your `xapp-...` token
   - `ANTHROPIC_API_KEY` = your `sk-ant-...` key
6. Railway will automatically redeploy with the new variables

### That's it

Railway auto-deploys on every push to `main`. Check the **Logs** tab to confirm the bot started successfully.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | Yes | — | Bot user OAuth token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | — | App-level token (`xapp-...`) |
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key |
| `SUMMARY_MODEL` | No | `claude-sonnet-4-6` | Claude model to use for summaries |
| `SUMMARY_MAX_TOKENS` | No | `1024` | Max tokens for summary response |

## Project Structure

```
├── bot/
│   ├── __init__.py
│   ├── app.py           # Slack event handlers and bot startup
│   ├── article.py       # URL extraction and article text fetching
│   ├── config.py        # Environment variable loading
│   ├── gdrive.py        # Google Drive / Docs file fetching and extraction
│   └── summarizer.py    # Claude-powered article summarization
├── .env.example         # Template for environment variables
├── Dockerfile           # Container build for deployment
├── railway.json         # Railway deployment config
├── pyproject.toml       # Python project metadata and dependencies
└── README.md
```

## Supported Link Types

The bot will attempt to summarize any HTTP/HTTPS link that looks like a news article. It automatically skips:

- YouTube / video links
- Twitter/X posts
- Image files (png, jpg, gif)
- Slack internal links
- Giphy links

### PDF links

Direct links to PDFs (e.g. `arxiv.org/pdf/...`, `example.com/report.pdf`) are downloaded and their text is extracted with pypdf. PDFs are detected from the file's contents, not the URL, so links without a `.pdf` extension work too. Scanned (image-only) PDFs have no extractable text and will return an error.

### Google Drive support

The bot has special handling for Google Drive and Google Docs links. Supported formats:

| Link type | Example | Notes |
|-----------|---------|-------|
| Google Docs | `docs.google.com/document/d/...` | Exported as plain text |
| Google Slides | `docs.google.com/presentation/d/...` | Exported as plain text |
| PDF on Drive | `drive.google.com/file/d/...` | Text extracted with pypdf |
| Word doc on Drive | `drive.google.com/file/d/...` | Text extracted with python-docx |

> **Requirement:** The file must be shared as **"Anyone with the link can view"**. Private files will return an error. Authentication is not supported.

## Troubleshooting

**Bot doesn't respond to links:**
- Make sure the bot is invited to the channel (`/invite @News Summarizer`)
- Check that `message.channels` is enabled under Event Subscriptions
- Look at the Railway logs for errors

**"Couldn't summarize this link" reply in Slack:**
- Some sites block automated requests. The bot will reply in-thread explaining whether the fetch or summarization step failed.
- If a site consistently blocks requests, the article fetcher in `bot/article.py` may need tweaking (see below).

**Bot responds to its own messages (loop):**
- This shouldn't happen — the bot filters out messages with `bot_id`. If it does, check that the Slack app has a proper bot user configured.

## Article Fetching — What We've Tweaked

Not every site makes it easy to grab article text. The fetcher (`bot/article.py`) has been iteratively improved to handle real-world sites. Here's what's in place and why:

| Layer | What it does | Why it was added |
|-------|-------------|-----------------|
| **trafilatura (default)** | Downloads and extracts article text using its built-in fetcher | Works out of the box for most sites |
| **Browser-like headers (fallback)** | Retries with a full set of headers (`User-Agent`, `Sec-Fetch-*`, `Accept`, etc.) mimicking a real Chrome browser | Added after sites like motor1.com returned 403 errors — they check for bot-like request headers |
| **PDF detection** | If the download starts with `%PDF`, the raw bytes are parsed with pypdf instead of the HTML extractor | arXiv and other PDF links were being fed to trafilatura as HTML, which returned nothing |
| **Skip patterns** | Ignores URLs that aren't articles (YouTube, Twitter/X, images, Slack links, Giphy) | Prevents unnecessary fetch attempts on non-article content |

### Known limitation: paywalled sites on cloud hosting

Some major news sites (NYTimes, Washington Post, etc.) block requests from cloud server IP addresses. Articles from these sites will work when running the bot locally (residential IP) but **fail when deployed to Railway or similar platforms**.

To fix this, you'd need to route requests through a residential proxy service such as [ScraperAPI](https://www.scraperapi.com/), [Bright Data](https://brightdata.com/), or [ScrapingBee](https://www.scrapingbee.com/). These add a small per-request cost but make cloud-hosted fetching indistinguishable from a normal browser.

### If a new site isn't working

1. Run the bot locally and check the logs — they'll show whether the download failed (403/timeout) or the extraction returned too little text
2. Common fixes:
   - **403 errors**: The site may need additional headers or cookie handling. Update `BROWSER_HEADERS` in `bot/article.py`
   - **Empty extraction**: trafilatura's parser may not understand the site's HTML structure. Try adjusting the `trafilatura.extract()` options (e.g., `favor_recall=True` instead of `favor_precision=True`)
   - **JavaScript-rendered sites**: Sites that load content via JavaScript won't work with any HTTP-based fetcher. These would require a headless browser (e.g., Playwright), which is a heavier dependency

## Changelog

### Direct PDF link support & clearer failure messages
**What changed:** The standard article fetcher now handles PDFs, `.pdf` links are no longer skipped, and the Slack error message now says *why* a link failed.

**Why:** An arXiv link (`arxiv.org/pdf/...`) failed with "the site blocked access", but arXiv hadn't blocked anything — it returned the PDF fine. The bot passed the PDF bytes to trafilatura, an HTML extractor, which returned nothing, and every failure was reported with the same "blocked" message. Links ending in `.pdf` were also silently ignored by the skip patterns.

**How it works:**
- `fetch_article` (`bot/article.py`) checks whether the download starts with `%PDF`. If so, it refetches the raw bytes (trafilatura decodes to lossy text) and parses them with `extract_pdf`, shared with the Drive fetcher in `bot/gdrive.py`.
- `fetch_article` raises `FetchError` with a user-facing reason instead of returning `None`: the site blocked access or didn't respond / the page had no readable article text / the PDF had no extractable text. `bot/app.py` includes that reason in the thread reply.

### Top-level-only summaries & duplicate-link dedup
**What changed:** Two behavior changes to reduce noise:
1. The bot now ignores links posted in thread replies and only summarizes links in top-level channel messages.
2. When a single message contains the same link more than once, the bot summarizes it only once instead of repeating the TL;DR.

**Why:**
- **Thread replies:** Once the bot replies in-thread, people often continue the conversation there and paste additional/related links. Those weren't the "news drop" the channel is for, so summarizing them cluttered the thread. Limiting to top-level posts keeps summaries tied to the intentional share.
- **Duplicate links:** Users frequently paste a hyperlinked title *and* the bare URL of the same article (common when copying from a browser or another app). The bot previously treated these as two links and posted the same summary twice.

**How it works:**
- **Top-level filter (`bot/app.py`):** Slack tags thread replies with a `thread_ts` that differs from the message's own `ts`. The handler now early-returns when `thread_ts` is present and `!= ts`. The bot's own in-thread replies were already filtered out by `bot_id`, so this cleanly targets human replies only.
- **Dedup (`bot/article.py`):** `extract_urls` now runs its results through an order-preserving dedup. URLs are compared using a normalized key — lowercased scheme/host, trailing slash stripped, and tracking params (`utm_*`, `fbclid`, `gclid`) removed — but the original URL form is what gets fetched. This catches both exact copy-paste duplicates and the "same article, slightly different URL" case.

### Google Drive & Docs support
**What changed:** Added `bot/gdrive.py`, a dedicated module for handling Google Drive and Google Docs links. Updated `bot/app.py` to route Drive URLs through this new fetcher instead of the standard article fetcher. Added `pypdf` and `python-docx` as dependencies.

**Why:** The standard article fetcher failed on Drive links because `drive.google.com` serves a JavaScript-rendered file preview page, not readable HTML. Even with browser-like headers, there's no article text to extract. Drive files need to be downloaded directly and parsed based on their file type.

**How it works:**
- Google Docs/Slides links are exported directly as plain text via Google's own export API (no scraping needed)
- `drive.google.com/file/d/...` links are downloaded as raw bytes, then the file type is detected from the first few bytes (magic bytes) rather than guessing from the URL
- PDFs are parsed with `pypdf`, Word docs with `python-docx`
- If the file isn't publicly shared, the bot replies with a clear error explaining the sharing requirement
