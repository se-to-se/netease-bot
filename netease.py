import re
import httpx


async def fetch_json(client: httpx.AsyncClient, api_base: str, path: str, params: dict) -> dict:
    resp = await client.get(f"{api_base}{path}", params=params)
    resp.raise_for_status()
    return resp.json()


async def get_song_info(client: httpx.AsyncClient, api_base: str, song_id: int) -> dict:
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


async def get_lyrics(client: httpx.AsyncClient, api_base: str, song_id: int) -> dict:
    data = await fetch_json(client, api_base, "/lyric", {"id": song_id})
    lrc = data.get("lrc") or {}
    tlyric = data.get("tlyric") or {}
    return {
        "original": lrc.get("lyric", ""),
        "translate": tlyric.get("lyric", ""),
    }


async def get_hot_comments(client: httpx.AsyncClient, api_base: str, song_id: int, limit: int = 5) -> list:
    data = await fetch_json(client, api_base, "/comment/music", {"id": song_id, "limit": limit})
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
    patterns = [
        r"id=(\d+)",
        r"/song/(\d+)",
        r"/song\?id=(\d+)",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return int(m.group(1))
    return None


def clean_lyrics(lrc_text: str) -> str:
    # Remove timestamp tags [00:00.00]
    cleaned = re.sub(r"\[.*?\]", "", lrc_text)
    # Remove metadata lines like: 作词 : xxx / 作曲 : xxx / 编曲 : xxx / 制作人 : xxx
    cleaned = re.sub(
        r"^(作词|作曲|编曲|制作人|演唱|混音|录音|母带|吉他|贝斯|键盘|鼓手|和声|和音|监制|发行)"
        r".*?[\r\n]+",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    # Remove "未经著作权人许可..." copyright notice
    cleaned = re.sub(r"^未经.*?[\r\n]+", "", cleaned, flags=re.MULTILINE)
    # Collapse multiple blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
