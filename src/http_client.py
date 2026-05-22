import asyncio
import dataclasses
import re
from urllib.parse import urlparse, unquote

from curl_cffi import requests


@dataclasses.dataclass(init=False)
class FileMetadataResult:
    def __init__(self):
        self.success: bool = False
        self.filename: str = ''
        self.size: int | None = None
        self.content_type: str = ""
        self.status_code: int | None = None
        self.error: str = ""


def extract_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    filename = unquote(path.split('/')[-1])
    if not filename:
        filename = 'unknown'
    return filename


def extract_filename_from_disposition(disposition: str) -> str | None:
    if not disposition:
        return None

    match = re.search(r"filename\*=([^']*)'[^']*'([^;\"]*)", disposition, re.IGNORECASE)
    if match:
        charset = match.group(1) or 'utf-8'
        try:
            filename = unquote(match.group(2), encoding=charset)
        except LookupError:
            filename = unquote(match.group(2))
        return filename

    match = re.search(r"filename=\"([^\"]+)\"", disposition, re.IGNORECASE)
    if match:
        return unquote(match.group(1))

    match = re.search(r'filename=([^";\s]+)', disposition, re.IGNORECASE)
    if match:
        return unquote(match.group(1))

    return None


async def get_file_metadata(url: str) -> FileMetadataResult:
    metadata = FileMetadataResult()

    if not url or not isinstance(url, str):
        metadata.error = 'Invalid URL'
        return metadata

    if not url.startswith(('http://', 'https://')):
        metadata.error = 'URL must start with http:// or https://'
        return metadata

    try:
        async with requests.AsyncSession() as session:
            response = await session.request(
                method="HEAD",
                url=url,
                allow_redirects=True,
                timeout=30,
                impersonate="chrome146"
            )

            metadata.status_code = response.status_code

            if response.status_code in [200, 206]:
                metadata.success = True
            else:
                metadata.error = f"HTTP {response.status_code}"

            content_type = response.headers.get('Content-Type', '')
            metadata.content_type = content_type

            content_length = response.headers.get('Content-Length')
            if content_length and content_length.isdigit():
                # noinspection PyTypeChecker
                metadata.size = int(content_length)

            disposition = response.headers.get('Content-Disposition', '')
            filename = extract_filename_from_disposition(disposition)

            if not filename:
                filename = extract_filename_from_url(url)

            metadata.filename = unquote(unquote(filename))

    except asyncio.TimeoutError:
        metadata.error = 'Request timed out'
    except requests.RequestsError as e:
        metadata.error = f"Request failed: {str(e)}"
    except Exception as e:
        metadata.error = f"Unexpected error: {str(e)}"

    return metadata
