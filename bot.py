import asyncio
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Per-chat language preference (in-memory, resets on restart)
USER_LANGS: dict[int, str] = {}

LANG_KEYS = {"zh": "中文", "en": "English", "ja": "日本語", "ru": "Русский"}

# ---- i18n strings ----------------------------------------------------------
T = {
    "welcome": {
        "zh": (
            "Hi! 发送网易云音乐链接给我，我帮你翻译歌词和热评。\n\n"
            "示例: https://music.163.com/song?id=722928"
        ),
        "en": (
            "Hi! Send me a NetEase Cloud Music link and I'll translate "
            "the lyrics and top comments for you.\n\n"
            "Example: https://music.163.com/song?id=722928"
        ),
        "ja": (
            "Hi! 网易云音乐のリンクを送ると、歌詞と人気コメントを翻訳します。\n\n"
            "例: https://music.163.com/song?id=722928"
        ),
        "ru": (
            "Привет! Пришли мне ссылку на NetEase Cloud Music, "
            "и я переведу текст песни и лучшие комментарии.\n\n"
            "Пример: https://music.163.com/song?id=722928"
        ),
    },
    "lang_prompt": {
        "zh": "选择界面语言 / Select language：",
        "en": "Select language / 选择界面语言：",
        "ja": "言語を選択 / Select language：",
        "ru": "Выберите язык / Select language：",
    },
    "invalid_link": {
        "zh": "请发送有效的网易云音乐链接。\n支持 163cn.tv 短链 和 music.163.com 标准链接",
        "en": "Please send a valid NetEase Cloud Music link.\nSupports 163cn.tv short links and music.163.com standard links",
        "ja": "有効な网易云音乐のリンクを送ってください。\n163cn.tv 短縮リンク と music.163.com 標準リンクに対応",
        "ru": "Отправьте действительную ссылку NetEase Cloud Music.\nПоддерживаются короткие ссылки 163cn.tv и стандартные music.163.com",
    },
    "pick_lang": {
        "zh": "选择翻译目标语言：",
        "en": "Pick translation language:",
        "ja": "翻訳言語を選択：",
        "ru": "Выберите язык перевода:",
    },
    "fetching": {
        "zh": "正在获取歌曲信息并翻译为{target}...",
        "en": "Fetching song info and translating to {target}...",
        "ja": "曲情報を取得し、{target}に翻訳中...",
        "ru": "Получение информации о песне и перевод на {target}...",
    },
    "api_error": {
        "zh": "获取歌曲信息失败，网易云API可能不可用。\n错误: {err}",
        "en": "Failed to fetch song info. The API may be unavailable.\nError: {err}",
        "ja": "曲情報の取得に失敗。APIが利用できない可能性があります。\nエラー: {err}",
        "ru": "Не удалось получить информацию о песне. API может быть недоступен.\nОшибка: {err}",
    },
    "song_not_found": {
        "zh": "未找到该歌曲，请检查链接是否正确。",
        "en": "Song not found. Please check the link.",
        "ja": "曲が見つかりません。リンクを確認してください。",
        "ru": "Песня не найдена. Проверьте ссылку.",
    },
    "lyrics_label": {
        "zh": lambda t: f"*歌词（{t}）*",
        "en": lambda t: f"*Lyrics ({t})*",
        "ja": lambda t: f"*歌詞（{t}）*",
        "ru": lambda t: f"*Текст песни ({t})*",
    },
    "lyrics_fail": {
        "zh": "*歌词翻译失败*",
        "en": "*Lyrics translation failed*",
        "ja": "*歌詞の翻訳に失敗*",
        "ru": "*Ошибка перевода текста*",
    },
    "comments_head": {
        "zh": lambda n, t: f"*热评 TOP{n}（{t}）*",
        "en": lambda n, t: f"*Top {n} Comments ({t})*",
        "ja": lambda n, t: f"*人気コメント TOP{n}（{t}）*",
        "ru": lambda n, t: f"*Топ-{n} комментариев ({t})*",
    },
    "truncated": {
        "zh": "(内容过长已截断)",
        "en": "(content truncated)",
        "ja": "(内容が長すぎるため切り捨て)",
        "ru": "(содержание обрезано)",
    },
    "tutorial_unconfigured": {
        "zh": "教程图片未配置。",
        "en": "Tutorial images not configured.",
        "ja": "チュートリアル画像が設定されていません。",
        "ru": "Изображения руководства не настроены.",
    },
    "tutorial_summary": {
        "zh": "教程图片已发送（{ok}/{total} 张成功）。",
        "en": "Tutorial images sent ({ok}/{total} successful).",
        "ja": "チュートリアル画像を送信しました（{ok}/{total} 枚成功）。",
        "ru": "Изображения руководства отправлены ({ok}/{total} успешно).",
    },
    "help_hint": {
        "zh": "输入 /help 查看教程图片。",
        "en": "Type /help to view tutorial images.",
        "ja": "/help でチュートリアル画像を表示。",
        "ru": "Введите /help для просмотра изображений руководства.",
    },
}


def _lang(update: Update) -> str:
    """Get the UI language for this chat. Default zh."""
    cid = update.effective_chat.id if update.effective_chat else 0
    return USER_LANGS.get(cid, "zh")


def _t(update: Update, key: str, **kwargs) -> str:
    """Look up a translated string; format with kwargs if provided."""
    lang = _lang(update)
    val = T.get(key, {}).get(lang) or T[key].get("zh", key)
    if callable(val):
        return val(**kwargs) if kwargs else val
    if kwargs:
        return str(val).format(**kwargs)
    return str(val)


# ---------------------------------------------------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show language selection first, then welcome."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("中文", callback_data="setlang_zh"),
            InlineKeyboardButton("English", callback_data="setlang_en"),
        ],
        [
            InlineKeyboardButton("日本語", callback_data="setlang_ja"),
            InlineKeyboardButton("Русский", callback_data="setlang_ru"),
        ],
    ])
    await update.message.reply_text(
        _t(update, "lang_prompt"),
        reply_markup=keyboard,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send 6 tutorial images one by one."""
    valid_images = [url for url in TUTORIAL_IMAGES if url.strip()]
    if not valid_images:
        await update.message.reply_text(_t(update, "tutorial_unconfigured"))
        return

    failed = 0
    for i, url in enumerate(valid_images[:6], 1):
        try:
            await update.message.reply_photo(photo=url)
            if i < len(valid_images[:6]):
                await asyncio.sleep(0.3)  # Prevent flood
        except Exception as e:
            logger.warning("Tutorial image %d failed: %s", i, e)
            failed += 1

    if failed:
        await update.message.reply_text(
            _t(update, "tutorial_summary", ok=len(valid_images[:6]) - failed,
               total=len(valid_images[:6]))
        )


async def gift_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Моей любимой Юне")


# ---- Language selection callback -------------------------------------------

async def _set_language_and_welcome(query, lang_code: str):
    """Save user language and send welcome message."""
    cid = query.message.chat_id
    USER_LANGS[cid] = lang_code
    await query.edit_message_text(_t(query, "welcome"))
    await query.message.reply_text(_t(query, "help_hint"))


# ---- Message / link handler ------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    timeout = httpx.Timeout(30.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        song_id = await find_song_id(client, text)

    if not song_id:
        await update.message.reply_text(_t(update, "invalid_link"))
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("中文", callback_data=f"zh_{song_id}"),
            InlineKeyboardButton("English", callback_data=f"en_{song_id}"),
        ],
        [
            InlineKeyboardButton("日本語", callback_data=f"ja_{song_id}"),
            InlineKeyboardButton("Русский", callback_data=f"ru_{song_id}"),
        ],
    ])
    await update.message.reply_text(_t(update, "pick_lang"), reply_markup=keyboard)


# ---- Unified callback handler -----------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Branch: language selection
    if data.startswith("setlang_"):
        lang_code = data.split("_")[1]
        await _set_language_and_welcome(query, lang_code)
        return

    # Branch: song translation
    lang_code, song_id_str = data.split("_", 1)
    song_id = int(song_id_str)
    target_lang = LANG_DISPLAY.get(lang_code.upper(), "英语")

    await query.edit_message_text(
        _t(query, "fetching", target=target_lang)
    )

    timeout = httpx.Timeout(30.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            song_info, lyrics_data, comments = await asyncio.gather(
                get_song_info(client, NETEASE_API_BASE, song_id),
                get_lyrics(client, NETEASE_API_BASE, song_id),
                get_hot_comments(client, NETEASE_API_BASE, song_id),
            )
        except httpx.HTTPError as e:
            await query.edit_message_text(
                _t(query, "api_error", err=str(e))
            )
            return
        except Exception as e:
            await query.edit_message_text(
                _t(query, "api_error", err=str(e))
            )
            return

        if not song_info:
            await query.edit_message_text(_t(query, "song_not_found"))
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
                result_parts.extend([
                    _t(query, "lyrics_label", t=target_lang),
                    clean_lyric_text[:1500], "",
                ])
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
                        result_parts.extend([
                            _t(query, "lyrics_label", t=target_lang),
                            translated, "",
                        ])
                    except Exception as e:
                        result_parts.extend([
                            _t(query, "lyrics_fail"),
                            f"{str(e)[:100]}\n{clean_lyric_text[:800]}",
                            "",
                        ])
                else:
                    result_parts.extend([
                        _t(query, "lyrics_label", t=target_lang),
                        clean_lyric_text[:1500], "",
                    ])

        # Hot comments
        if comments:
            result_parts.append(
                _t(query, "comments_head", n=str(len(comments)), t=target_lang)
            )
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

    trunc = _t(query, "truncated")
    if len(final_text) > 4000:
        final_text = final_text[:4000 - len(trunc) - 4] + f"\n\n{trunc}"

    try:
        await query.edit_message_text(final_text, parse_mode="Markdown")
    except Exception:
        plain_text = "\n".join(
            p.replace("*", "").replace("_", "") for p in result_parts
        )
        if len(plain_text) > 4000:
            plain_text = plain_text[:4000 - len(trunc) - 4] + f"\n\n{trunc}"
        await query.edit_message_text(plain_text)


# ---- Main ------------------------------------------------------------------

def main():
    app = Application.builder().token(TG_BOT_TOKEN).build()

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
