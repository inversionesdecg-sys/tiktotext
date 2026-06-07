"""
Obtiene listas de URLs de TikTok.

Dos estrategias:
  - Colecciones: Playwright intercepta la petición firmada en /favorites,
    luego pagina con requests.
  - Me gusta / videos de colección: TikTokApi con el browser del usuario.
"""
import asyncio
import requests
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote

from config.settings import TIKTOK_COOKIES, TIKTOK_LIKED_LIMIT, get_tiktok_user, get_browser_path


# ── Helpers de cookies ────────────────────────────────────────────────────────

def _load_cookies() -> dict:
    """
    Lee el archivo de cookies TikTok del usuario (~/.tiktotex/tiktok_cookies.txt)
    en formato Netscape y devuelve {name: value} filtrando por tiktok.com.
    """
    cookies: dict[str, str] = {}
    with open(TIKTOK_COOKIES, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, _path, _secure, _expiry, name, value = parts[:7]
            if "tiktok.com" not in domain:
                continue
            if name and value and "\n" not in value and "\r" not in value:
                cookies[name] = value
    return cookies


def _to_playwright_cookies(cookies: dict) -> list[dict]:
    return [
        {"name": k, "value": v, "domain": ".tiktok.com", "path": "/"}
        for k, v in cookies.items()
    ]


# ── TikTokApi (Me gusta y videos de colección) ────────────────────────────────

async def _make_api_session(cookies: dict):
    """Abre sesión TikTokApi con el browser del usuario."""
    from TikTokApi import TikTokApi
    ms_token = cookies.get("msToken")
    api = TikTokApi()
    await api.create_sessions(
        cookies=[cookies],
        num_sessions=1,
        ms_tokens=[ms_token] if ms_token else None,
        executable_path=get_browser_path(),
        headless=True,
    )
    return api


async def _fetch_liked_urls(cookies: dict) -> list[str]:
    """Devuelve URLs de los videos con Me gusta."""
    tiktok_user = get_tiktok_user()
    print(f"  Abriendo sesion TikTokApi - Me gusta de @{tiktok_user}...")
    urls: list[str] = []
    api = await _make_api_session(cookies)
    async with api:
        async for video in api.user(tiktok_user).liked(count=TIKTOK_LIKED_LIMIT):
            urls.append(
                f"https://www.tiktok.com/@{video.author.username}/video/{video.id}"
            )
            if len(urls) % 50 == 0:
                print(f"  ... {len(urls)} URLs")
    return urls


async def _fetch_collection_urls(
    cookies: dict, collection_id: str, collection_name: str = ""
) -> list[str]:
    """
    Navega a @user/collection/{name}-{id}, intercepta la petición firmada
    a /api/collection/item_list/ y pagina con requests cambiando `cursor`.
    """
    from playwright.async_api import async_playwright

    tiktok_user = get_tiktok_user()
    # TikTok usa el nombre de la colección en la URL, URL-encoded sin mayúsculas
    slug     = quote(collection_name.lower().replace(" ", "-"), safe="-") if collection_name else ""
    page_url = f"https://www.tiktok.com/@{tiktok_user}/collection/{slug}-{collection_id}" if slug else \
               f"https://www.tiktok.com/@{tiktok_user}/collection/{collection_id}"
    captured: dict = {}

    print(f"  Navegando a colección: {page_url}")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=get_browser_path(), headless=True
        )
        ctx = await browser.new_context()
        await ctx.add_cookies(_to_playwright_cookies(cookies))
        page = await ctx.new_page()

        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Network.enable")

        def _on_request(event: dict) -> None:
            req = event.get("request", {})
            url = req.get("url", "")
            if "api/collection/item_list" in url and "url" not in captured:
                captured["url"]     = url
                captured["headers"] = req.get("headers", {})

        cdp.on("Network.requestWillBeSent", _on_request)

        try:
            async with page.expect_response(
                lambda r: "api/collection/item_list" in r.url, timeout=20_000
            ):
                await page.goto(page_url, wait_until="domcontentloaded")
        except Exception:
            pass

        await asyncio.sleep(1)
        await browser.close()

    if not captured.get("url"):
        print("  No se pudo interceptar item_list.")
        return []

    # Paginar reutilizando la URL firmada, cambiando solo cursor
    headers = {**captured["headers"]}
    headers["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers.pop("Referer", None)

    parsed = urlparse(captured["url"])
    params = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}

    urls: list[str] = []
    cursor = 0
    while True:
        params["cursor"] = str(cursor)
        resp = requests.get(
            urlunparse(parsed._replace(query=urlencode(params))),
            headers=headers,
            timeout=15,
        )
        data  = resp.json()
        batch = data.get("itemList", [])
        if not batch:
            break
        for item in batch:
            vid_id = item.get("id", "")
            author = (item.get("author") or {}).get("uniqueId", "")
            if vid_id and author:
                urls.append(f"https://www.tiktok.com/@{author}/video/{vid_id}")
        print(f"  ... {len(urls)} URLs")
        if not data.get("hasMore", False):
            break
        cursor = int(data.get("cursor", cursor + len(batch)))

    return urls


# ── Colecciones vía intercepción de red ───────────────────────────────────────

async def _fetch_collections(cookies: dict) -> list[dict]:
    """
    Navega a /favorites con el browser del usuario y captura la petición firmada
    que TikTok genera para /api/user/collection_list/.
    Luego pagina esa URL desde Python cambiando solo `cursor`.
    """
    from playwright.async_api import async_playwright

    tiktok_user = get_tiktok_user()
    captured: dict = {}

    print(f"  Abriendo browser -> TikTok Favoritos de @{tiktok_user}...")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path=get_browser_path(), headless=True
        )
        ctx = await browser.new_context()
        await ctx.add_cookies(_to_playwright_cookies(cookies))
        page = await ctx.new_page()

        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Network.enable")

        def _on_request(event: dict) -> None:
            req = event.get("request", {})
            if "user/collection_list" in req.get("url", "") and "url" not in captured:
                captured["url"] = req["url"]
                captured["headers"] = req.get("headers", {})

        cdp.on("Network.requestWillBeSent", _on_request)

        try:
            async with page.expect_response(
                lambda r: "collection_list" in r.url, timeout=20_000
            ):
                await page.goto(
                    f"https://www.tiktok.com/@{tiktok_user}/favorites",
                    wait_until="domcontentloaded",
                )
        except Exception:
            pass

        await asyncio.sleep(1)
        await browser.close()

    if not captured.get("url"):
        print("  No se pudo interceptar la petición de colecciones.")
        return []

    # Paginar reutilizando la URL firmada, solo cambiando cursor
    headers = {**captured["headers"]}
    headers["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers.pop("Referer", None)

    parsed = urlparse(captured["url"])
    params = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}

    items: list[dict] = []
    cursor = 0
    while True:
        params["cursor"] = str(cursor)
        resp = requests.get(
            urlunparse(parsed._replace(query=urlencode(params))),
            headers=headers,
            timeout=15,
        )
        data = resp.json()
        batch = data.get("collectionList", [])
        if not batch:
            break
        items.extend(batch)
        print(f"  ... {len(items)} colecciones")
        if not data.get("hasMore", False):
            break
        cursor = int(data.get("cursor", cursor + len(batch)))

    return [
        {
            "id":    item.get("collectionId", "?"),
            "name":  item.get("name", "sin nombre"),
            "count": item.get("total", "?"),
        }
        for item in items
    ]


# ── API pública ───────────────────────────────────────────────────────────────

def get_tiktok_collections() -> list[dict]:
    print("Leyendo carpetas de Favoritos TikTok...")
    result = asyncio.run(_fetch_collections(_load_cookies()))
    print(f"  {len(result)} colecciones encontradas.")
    return result


def get_tiktok_liked_urls() -> list[str]:
    tiktok_user = get_tiktok_user()
    print(f"Obteniendo Me gusta de @{tiktok_user}...")
    urls = asyncio.run(_fetch_liked_urls(_load_cookies()))
    print(f"  {len(urls)} URLs obtenidas.")
    return urls


def get_tiktok_collection_urls(collection_id: str, collection_name: str = "") -> list[str]:
    label = collection_name or collection_id
    print(f"Obteniendo videos de colección '{label}'...")
    urls = asyncio.run(_fetch_collection_urls(_load_cookies(), collection_id, collection_name))
    print(f"  {len(urls)} URLs obtenidas.")
    return urls
