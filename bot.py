import asyncio
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from config import (
    TG_BOT_TOKEN, BAIDU_APP_ID, BAIDU_SECRET_KEY,
    NETEASE_API_BASE, TUTORIAL_IMAGES,
)
from netease import (
    find_song_id, get_song_info, get_lyrics, get_hot_comments, clean_lyrics,
)
from translate import translate, LANG_DISPLAY

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "Hi! 发送网易云音乐链接给我，我帮你翻译歌词和热评。\n\n"
    "支持的翻译语言：中文 / 日语 / 俄语 / 英语\n\n"
    "示例: https://music.163.com/#/song?id=722928"
)


async def _send_tutorial(update: Update):
    """Send tutorial images (if configured) followed by welcome text."""
    valid_images = [url for url in TUTORIAL_IMAGES if url.strip()]
    if valid_images:
        media = [InputMediaPhoto(media=url) for url in valid_images[:6]]
        await update.message.reply_media_group(media=media)
    await update.message.reply_text(WELCOME_TEXT)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_tutorial(update)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_tutorial(update)


async def gift_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Моей любимой Юне")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    timeout = httpx.Timeout(30.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        song_id = await find_song_id(client, text)

    if not song_id:
        await update.message.reply_text(
            "请发送有效的网易云音乐链接。\n"
            "支持 163cn.tv 短链 和 music.163.com 标准链接\n"
            "格式示例: https://music.163.com/#/song?id=722928"
        )
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("中文", callback_data=f"zh_{song_id}"),
            InlineKeyboardButton("日本語", callback_data=f"ja_{song_id}"),
        ],
        [
            InlineKeyboardButton("Русский", callback_data=f"ru_{song_id}"),
            InlineKeyboardButton("English", callback_data=f"en_{song_id}"),
        ],
    ])
    await update.message.reply_text(
        "Pick translation language / 选择翻译语言：",
        reply_markup=keyboard,
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang_code, song_id_str = query.data.split("_", 1)
    song_id = int(song_id_str)
    target_lang = LANG_DISPLAY.get(lang_code.upper(), "英语")

    await query.edit_message_text(f"正在获取歌曲信息并翻译为{target_lang}...")

    timeout = httpx.Timeout(30.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            song_info, lyrics_data, comments = await asyncio.gather(
                get_song_info(client, NETEASE_API_BASE, song_id),
                get_lyrics(client, NETEASE_API_BASE, song_id),
                get_hot_comments(client, NETEASE_API_BASE, song_id),
            )
        except httpx.HTTPError as e:
            await query.edit_message_text(f"获取歌曲信息失败，网易云API可能不可用。\n错误: {e}")
            return
        except Exception as e:
            await query.edit_message_text(f"获取歌曲信息失败: {e}")
            return

        if not song_info:
            await query.edit_message_text("未找到该歌曲，请检查链接是否正确。")
            return

        result_parts = [
            f"*{song_info['name']}* - {song_info['artist']}",
            "",
        ]

        # Lyrics
        raw_lyric = lyrics_data.get("original", "")
        tlyric = lyrics_data.get("translate", "")

        if tlyric and lang_code == "zh":
            clean_lyric_text = clean_lyrics(tlyric)
            if clean_lyric_text:
                result_parts.extend(["*歌词（中文）*", clean_lyric_text[:1500], ""])
        elif raw_lyric:
            clean_lyric_text = clean_lyrics(raw_lyric)
            if clean_lyric_text:
                if lang_code != "zh":
                    try:
                        chunk = clean_lyric_text[:2000]
                        translated = await translate(
                            client, chunk, target_lang,
                            BAIDU_APP_ID, BAIDU_SECRET_KEY,
                        )
                        result_parts.extend([f"*歌词（{target_lang}）*", translated, ""])
                    except Exception as e:
                        result_parts.extend([
                            f"*歌词翻译失败*: {str(e)[:100]}",
                            clean_lyric_text[:800],
                            "",
                        ])
                else:
                    result_parts.extend(["*歌词*", clean_lyric_text[:1500], ""])

        # Hot comments
        if comments:
            result_parts.append(f"*热评 TOP{len(comments)}（{target_lang}）*")
            result_parts.append("")

            for i, c in enumerate(comments, 1):
                content = c["content"]
                nickname = c["nickname"]
                likes = c["liked_count"]

                if lang_code == "zh":
                    translated = content
                else:
                    try:
                        await asyncio.sleep(0.6)
                        translated = await translate(
                            client, content[:500], target_lang,
                            BAIDU_APP_ID, BAIDU_SECRET_KEY,
                        )
                    except Exception as e:
                        logger.warning("Comment %d translation failed: %s", i, e)
                        translated = content

                result_parts.append(f"{i}. {nickname} [👍{likes}]")
                result_parts.append(f"_{translated}_")
                result_parts.append("")

    final_text = "\n".join(result_parts)

    if len(final_text) > 4000:
        final_text = final_text[:3950] + "\n\n...(内容过长已截断)"

    try:
        await query.edit_message_text(final_text, parse_mode="Markdown")
    except Exception:
        plain_text = "\n".join(
            p.replace("*", "").replace("_", "") for p in result_parts
        )
        if len(plain_text) > 4000:
            plain_text = plain_text[:3950] + "\n\n...(内容过长已截断)"
        await query.edit_message_text(plain_text)


def main():
    app = Application.builder().token(TG_BOT_TOKEN).build()

    # Easter egg: "gift" triggers a hidden message (must be checked before generic handler)
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"(?i)^\s*gift\s*$"), gift_handler,
    ))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message,
    ))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
