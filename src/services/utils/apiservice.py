import asyncio
import base64
import ssl
from io import BytesIO

import aiohttp
import certifi

_ssl_context = ssl.create_default_context(cafile=certifi.where())
_connector: aiohttp.TCPConnector | None = None


def init_http_connector():
    global _connector
    _connector = aiohttp.TCPConnector(
        ssl=_ssl_context,
        limit=500,
        limit_per_host=100,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )


async def close_http_connector():
    global _connector
    if _connector and not _connector.closed:
        await _connector.close()
    _connector = None


def _get_connector() -> aiohttp.TCPConnector:
    if _connector is None or _connector.closed:
        # Fallback if called before startup (e.g. tests)
        init_http_connector()
    return _connector


async def fetch(url, method="GET", headers=None, params=None, json_body=None, image=None):
    timeout = aiohttp.ClientTimeout(total=600, connect=15)
    async with aiohttp.ClientSession(connector=_get_connector(), connector_owner=False, timeout=timeout) as session:
        body = None if method.upper() == "GET" else json_body
        async with session.request(
            method=method, url=url, headers=headers, params=params, json=body
        ) as response:
            if response.status >= 300:
                error_response = await response.text()
                raise ValueError(error_response)
            if image:
                response_data = BytesIO(await response.read())
            else:
                response_data = await response.json()
            response_headers = dict(response.headers)
            return response_data, response_headers


async def fetch_stream(url, method="POST", headers=None, json_body=None):
    """Async generator that yields raw SSE lines from a streaming HTTP response."""
    # 10 MiB buffer — large enough for SSE lines that embed base64 payloads
    # (e.g. OpenAI ``response.image_generation_call.partial_image``), which
    # exceed aiohttp's default ~128 KB per-line limit.
    timeout = aiohttp.ClientTimeout(total=900, connect=15, sock_read=120)
    async with aiohttp.ClientSession(
        connector=_get_connector(),
        connector_owner=False,
        read_bufsize=64 * 1024 * 1024,
        timeout=timeout,
    ) as session:
        async with session.request(
            method=method, url=url, headers=headers, json=json_body
        ) as response:
            if response.status >= 300:
                error_response = await response.text()
                raise ValueError(error_response)
            async for line in response.content:
                decoded = line.decode("utf-8").strip()
                if decoded:
                    yield decoded


async def fetch_images_b64(urls):
    if not urls:
        return []
    images_res, headers = zip(*await asyncio.gather(*(fetch(url, image=True) for url in urls)), strict=False)
    images_data = [base64.b64encode(image.getvalue()).decode("utf-8") for image in images_res]
    images_media_type = [header.get("Content-Type") for header in headers]
    return zip(images_data, images_media_type, strict=False)
