import logging
import re

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from app.config import settings
from app.agent import get_response

logger = logging.getLogger(__name__)

slack_app = AsyncApp(token=settings.slack_bot_token)
socket_handler = AsyncSocketModeHandler(slack_app, settings.slack_app_token)


async def build_thread_history(client, channel: str, thread_ts: str, bot_user_id: str) -> list[dict]:
    """Fetch thread messages and convert to role/content history for the LLM."""
    result = await client.conversations_replies(channel=channel, ts=thread_ts)
    messages = result.get("messages", [])
    history = []
    for msg in messages:
        text = re.sub(r"<@\w+>", "", msg.get("text", "")).strip()
        if not text:
            continue
        is_bot = msg.get("bot_id") or msg.get("user") == bot_user_id
        history.append({"role": "assistant" if is_bot else "user", "content": text[:4000]})
    return history


@slack_app.event("app_mention")
async def handle_mention(event, client, say):
    logger.info(f"Handling app_mention event: {event}")
    thread_ts = event.get("thread_ts") or event.get("ts")
    channel = event["channel"]
    try:
        bot_info = await client.auth_test()
        bot_user_id = bot_info["user_id"]

        if event.get("thread_ts"):
            # In an existing thread — send full history
            messages = await build_thread_history(client, channel, thread_ts, bot_user_id)
        else:
            # New top-level mention — just the current message
            raw_text = event.get("text", "")
            text = re.sub(r"<@\w+>", "", raw_text).strip()
            if not text:
                return
            messages = [{"role": "user", "content": text[:4000]}]

        if not messages:
            return

        reply = await get_response(messages)
        await say(text=reply, thread_ts=thread_ts)
    except Exception:
        logger.exception("Error handling app_mention")
        await say(text="Sorry, something went wrong.", thread_ts=thread_ts)


@slack_app.event("message")
async def handle_thread_message(event, client, say):
    # Only handle messages inside threads, not top-level posts
    logger.info(f"Handling thread message event: {event}")
    thread_ts = event.get("thread_ts")
    if not thread_ts or event.get("ts") == thread_ts:
        logger.info("handle_thread_message: skipping — not a thread reply")
        return

    # Ignore bot messages and mentions (handled by handle_mention)
    if event.get("bot_id") or event.get("subtype"):
        logger.info("handle_thread_message: skipping — bot message or subtype")
        return
    if re.search(r"<@\w+>", event.get("text", "")):
        logger.info("handle_thread_message: skipping — contains mention")
        return

    channel = event["channel"]

    try:
        bot_info = await client.auth_test()
        bot_user_id = bot_info["user_id"]

        messages = await build_thread_history(client, channel, thread_ts, bot_user_id)
        logger.info(f"handle_thread_message: thread history has {len(messages)} messages: {messages}")

        bot_was_in_thread = any(m["role"] == "assistant" for m in messages[:-1])
        if not bot_was_in_thread:
            logger.info("handle_thread_message: skipping — bot not in thread")
            return

        if not messages:
            return

        reply = await get_response(messages)
        await say(text=reply, thread_ts=thread_ts)
    except Exception:
        logger.exception("Error handling thread message")
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
        slack_messages = result.get("messages", [])
        if not slack_messages:
            return

        message = slack_messages[0]

        # Skip if the message is from the bot itself
        bot_info = await client.auth_test()
        if message.get("bot_id") or message.get("user") == bot_info["user_id"]:
            return

        text = message.get("text", "").strip()
        if not text:
            return

        reply = await get_response([{"role": "user", "content": text[:4000]}])
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