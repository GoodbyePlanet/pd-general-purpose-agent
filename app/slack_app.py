import logging
import re

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from app.config import settings
from app.agent import get_response

logger = logging.getLogger(__name__)

slack_app = AsyncApp(token=settings.slack_bot_token)
socket_handler = AsyncSocketModeHandler(slack_app, settings.slack_app_token)


@slack_app.event("app_mention")
async def handle_mention(event, say):
    logger.info(f"Handling app_mention event: {event}")
    thread_ts = event.get("thread_ts") or event.get("ts")
    try:
        raw_text = event.get("text", "")
        text = re.sub(r"<@\w+>", "", raw_text).strip()

        if not text:
            return

        # Truncate to avoid sending huge messages to the LLM
        reply = await get_response(text[:4000])
        await say(text=reply, thread_ts=thread_ts)
    except Exception:
        logger.exception("Error handling app_mention")
        await say(text="Sorry, something went wrong.", thread_ts=thread_ts)


@slack_app.event("reaction_added")
async def handle_reaction(event, client):
    logger.info(f"Handling reaction_added event: {event}")
    if event.get("reaction") != settings.trigger_emoji:
        return

    channel = event["item"]["channel"]
    message_ts = event["item"]["ts"]

    try:
        result = await client.conversations_history(
            channel=channel,
            latest=message_ts,
            inclusive=True,
            limit=1,
        )
        messages = result.get("messages", [])
        if not messages:
            return

        message = messages[0]

        # Skip if the message is from the bot itself
        bot_info = await client.auth_test()
        if message.get("bot_id") or message.get("user") == bot_info["user_id"]:
            return

        text = message.get("text", "").strip()
        if not text:
            return

        reply = await get_response(text[:4000])
        await client.chat_postMessage(
            channel=channel,
            thread_ts=message_ts,
            text=reply,
        )
    except Exception:
        logger.exception("Error handling reaction_added")
        try:
            await client.chat_postMessage(
                channel=channel,
                thread_ts=message_ts,
                text="Sorry, something went wrong.",
            )
        except Exception:
            logger.exception("Failed to send error message")