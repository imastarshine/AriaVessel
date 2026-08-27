from yadisk.sessions.async_httpx_session import AsyncHTTPXSession

from src.logger import logger
import yadisk
import src.shared

proxy_session = AsyncHTTPXSession(proxy=src.shared.YADISK_URL_PROXY) if src.shared.YADISK_URL_PROXY else None


class YDisk:
    def __init__(self):
        self.client = None

    async def init(self):
        self.client = yadisk.AsyncClient(
            token=src.shared.YADISK_TOKEN,
            session=proxy_session
        )

    async def check(self):
        try:
            return await self.client.check_token()
        except Exception as e:
            logger.exception(f'an error occurred on token check: {e}', exc_info=True)
            return False

    async def ensure_path(self, path: str):
        clean_path = path.replace("app:/", "").strip("/")
        parts = clean_path.split("/")

        if len(parts) < 2:
            return

        current = "app:/"
        for part in parts[:-1]:
            if not part:
                continue

            current += f"{part}/"
            if not await self.client.exists(current):
                try:
                    await self.client.mkdir(current)
                except Exception as e:
                    logger.warning(f"could not create directory {current}: {e}")

    async def upload(self, file_path: str, target_path: str):
        await self.ensure_path(target_path)
        with open(file_path, "rb") as f:
            await self.client.upload(f, target_path, overwrite=True)
