"""Slack bot that listens for links and replies with article summaries."""

import logging
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from bot.article import FetchError, extract_urls, fetch_article
from bot.config import SLACK_APP_TOKEN, SLACK_BOT_TOKEN
from bot.gdrive import fetch_drive_file, is_drive_url
from bot.summarizer import summarize

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = App(token=SLACK_BOT_TOKEN)


@app.event("message")
def handle_message(event, say):
    """Process new messages, look for URLs, summarize articles."""
    logger.info("Received message event: %s", event)

    # Ignore bot messages and edits
    if event.get("bot_id") or event.get("subtype"):
        logger.info("Skipping: bot_id=%s subtype=%s", event.get("bot_id"), event.get("subtype"))
        return

    # Only summarize top-level posts, not replies inside a thread. Thread replies
    # carry a thread_ts that differs from the message's own ts.
    thread_ts_field = event.get("thread_ts")
    if thread_ts_field and thread_ts_field != event.get("ts"):
        logger.info("Skipping thread reply: thread_ts=%s ts=%s", thread_ts_field, event.get("ts"))
        return

    text = event.get("text", "")
    urls = extract_urls(text)
    logger.info("Extracted URLs: %s", urls)

    if not urls:
        return

    channel = event["channel"]
    thread_ts = event["ts"]  # Reply in thread to the original message

    for url in urls:
        logger.info("Processing URL: %s", url)

        # Route Google Drive / Docs links through the dedicated fetcher
        if is_drive_url(url):
            logger.info("Detected Google Drive/Docs URL, using Drive fetcher")
            article_text = fetch_drive_file(url)
            if not article_text:
                say(
                    text="_Couldn't read this Google Drive file — make sure it's shared publicly (Anyone with the link). Supported formats: Google Docs, PDFs, and Word documents._",
                    channel=channel,
                    thread_ts=thread_ts,
                )
                continue
        else:
            try:
                article_text = fetch_article(url)
            except FetchError as e:
                logger.info("Could not extract article from %s: %s", url, e)
                say(
                    text=f"_Couldn't summarize this link — {e}._\n{url}",
                    channel=channel,
                    thread_ts=thread_ts,
                )
                continue

        summary = summarize(article_text, url)
        if not summary:
            logger.info("Could not summarize: %s", url)
            say(
                text=f"_Fetched the article but the summarization failed — this can happen if the content is too short or in an unexpected format._\n{url}",
                channel=channel,
                thread_ts=thread_ts,
            )
            continue

        say(
            text=summary,
            channel=channel,
            thread_ts=thread_ts,
        )
        logger.info("Posted summary for: %s", url)


@app.event("app_mention")
def handle_mention(event, say):
    """Respond when someone @mentions the bot."""
    say(
        text="👋 I automatically summarize news articles posted in this channel. "
        "Just drop a link and I'll reply with a summary!",
        channel=event["channel"],
        thread_ts=event.get("ts"),
    )


def main():
    logger.info("Starting News Summarizer Bot...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    main()
