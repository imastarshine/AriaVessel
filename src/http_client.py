import asyncio
import re
from typing import Dict
from urllib.parse import urlparse, unquote

from curl_cffi import requests


def extract_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    filename = unquote(path.split('/')[-1])
    if not filename:
        filename = 'unknown'
    return filename

def extract_filename_from_disposition(disposition: str) -> str | None:
    if not disposition:
        return None

    match = re.search(r"filename\*=[^']+'([^']+)'([^;\"]*)", disposition, re.IGNORECASE)
    if match:
        charset = match.group(1) or 'utf-8'
        filename = unquote(match.group(2), encoding=charset)
        return filename

    match = re.search(r"filename=\"([^\"]+)\"", disposition, re.IGNORECASE)
    if match:
        return unquote(match.group(1))
    
    match = re.search(r'filename=([^";\s]+)', disposition, re.IGNORECASE)
    if match:
        return unquote(match.group(1))
    
    return None

async def get_file_metadata(url: str) -> Dict[str, any]:
    """Fetch file metadata using HEAD request with curl_cffi.
    
    Args:
        url: The URL to fetch metadata from
    
    Returns:
        Dictionary with keys:
        - success (bool): True if request succeeded
        - filename (str): Parsed filename
        - size (int): File size in bytes, or None
        - content_type (str): MIME type
        - status_code (int): HTTP status code
        - error (str): Error message if success=False
    """
    result = {
        'success': False,
        'filename': '',
        'size': None,
        'content_type': '',
        'status_code': None,
        'error': ''
    }
    
    if not url or not isinstance(url, str):
        result['error'] = 'Invalid URL'
        return result

    if not url.startswith(('http://', 'https://')):
        result['error'] = 'URL must start with http:// or https://'
        return result

    try:
        async with requests.AsyncSession() as session:
            response = await session.request(
                method="HEAD",
                url=url,
                allow_redirects=True,
                timeout=30,
                impersonate="chrome146"
            )
            
            result['status_code'] = response.status_code

            if response.status_code in [200, 206]:
                result['success'] = True
            else:
                result['error'] = f"HTTP {response.status_code}"
                
            content_type = response.headers.get('Content-Type', '')
            result['content_type'] = content_type
            
            content_length = response.headers.get('Content-Length')
            if content_length and content_length.isdigit():
                result['size'] = int(content_length)

            disposition = response.headers.get('Content-Disposition', '')
            filename = extract_filename_from_disposition(disposition)
            
            if not filename:
                filename = extract_filename_from_url(url)
                
            result['filename'] = filename
            
    except asyncio.TimeoutError:
        result['error'] = 'Request timed out'
    except requests.RequestsError as e:
        result['error'] = f"Request failed: {str(e)}"
    except Exception as e:
        result['error'] = f"Unexpected error: {str(e)}"
    
    return result