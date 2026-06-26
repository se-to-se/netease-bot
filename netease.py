import asyncio
import logging
import re
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

SHORT_HOSTS = ("163cn.tv", "y.music.163.com")


async def fetch_json(
    client: httpx.AsyncClient, api_base: str, path: str, params: dict
) -> dict:
    resp = await client.get(f"{api_base}{path}", params=params)
    resp.raise_for_status()
    return resp.json()


async def get_song_info(
    client: httpx.AsyncClient, api_base: str, song_id: int
) -> dict:
    data = await fetch_json(client, api_base, "/song/detail", {"ids": song_id})
    songs = data.get("songs") or []
    if not songs:
        return {}
    song = songs[0]
    return {
        "name": song.get("name", "未知歌曲"),
        "artist": " / ".join(a["name"] for a in song.get("ar", [])),
        "album": (song.get("al") or {}).get("name", ""),
    }


async def get_lyrics(
    client: httpx.AsyncClient, api_base: str, song_id: int
) -> dict:
    data = await fetch_json(client, api_base, "/lyric", {"id": song_id})
    lrc = data.get("lrc") or {}
    tlyric = data.get("tlyric") or {}
    return {
        "original": lrc.get("lyric", ""),
        "translate": tlyric.get("lyric", ""),
    }


async def get_hot_comments(
    client: httpx.AsyncClient, api_base: str, song_id: int, limit: int = 5
) -> list:
    data = await fetch_json(
        client, api_base, "/comment/music", {"id": song_id, "limit": limit}
    )
    hot = data.get("hotComments") or []
    return [
        {
            "content": c["content"],
            "nickname": c["user"]["nickname"],
            "liked_count": c.get("likedCount", 0),
        }
        for c in hot[:limit]
    ]


def parse_song_id(text: str) -> int | None:
    """Try to extract a NetEase song ID from text containing a direct link."""
    patterns = [
        r"id=(\d+)",
        r"/song/(\d+)",
        r"/song\?id=(\d+)",
        r"song/(\d+)/",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return int(m.group(1))
    return None


def extract_urls(text: str) -> list:
    """Extract all HTTP URLs from a text string."""
    return re.findall(r"https?://[^\s]+", text)


def is_short_url(url: str) -> bool:
    """Check if a URL is a NetEase short-link that needs resolving."""
    return any(host in url for host in SHORT_HOSTS)


async def resolve_short_url(
    client: httpx.AsyncClient, short_url: str
) -> Optional[str]:
    """Follow redirects on a 163cn.tv / y.music.163.com link to get the real URL."""
    try:
        resp = await client.head(short_url, follow_redirects=True)
        return str(resp.url)
    except httpx.HTTPError as e:
        logger.warning("Failed to resolve short URL %s: %s", short_url, e)
        return None


async def find_song_id(
    client: httpx.AsyncClient, text: str
) -> Optional[int]:
    """
    Extract a song ID from user text.
    Handles both direct links (music.163.com) and short links (163cn.tv).
    """
    # First try direct parse
    sid = parse_song_id(text)
    if sid:
        return sid

    # Extract URLs and try short links
    urls = extract_urls(text)
    for url in urls:
        if is_short_url(url):
            real_url = await resolve_short_url(client, url)
            if real_url:
                sid = parse_song_id(real_url)
                if sid:
                    return sid

    return None


def clean_lyrics(lrc_text: str) -> str:
    # Remove timestamp tags [00:00.00]
    cleaned = re.sub(r"\[.*?\]", "", lrc_text)
    # Remove credit/metadata lines (allow leading whitespace)
    cleaned = re.sub(
        r"^\s*(?:作词|作曲|编曲|制作人|演唱|混音|录音|母带|吉他|贝斯|键盘|"
        r"鼓手|和声|和音|监制|发行|文案|封面|翻译|Lyricist|Composer)"
        r".*?[\r\n]+",
        "",
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Remove "未经著作权人许可..." copyright notice
    cleaned = re.sub(r"^\s*未经.*?[\r\n]+", "", cleaned, flags=re.MULTILINE)
    # Collapse multiple blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
