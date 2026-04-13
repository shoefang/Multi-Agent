"""下载图片"""

import hashlib
import hmac
import uuid
import time
import logging
from typing import Optional, Dict, Any, List
import requests
from datetime import datetime
from urllib.parse import quote
from typing import Optional, Dict, Any
import os
import re
from PIL import Image
import time
from pathlib import Path
import base64
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
from concurrent.futures import ThreadPoolExecutor
import time

def download_image(image_url):
    '''
    158s
    '''
    result = {}

    try:
        os.environ['http_proxy'] = 'http://agent.baidu.com:8891'
        os.environ['https_proxy'] = 'http://agent.baidu.com:8891'

        with requests.get(image_url, stream=True, timeout=(10, 300)) as r:
            #print(r.headers.get("Content-Length"))
            print("文件大小:", r.headers.get("Content-Length"))
            print("是否支持断点:", r.headers.get("Accept-Ranges"))
            r.raise_for_status()

            image_bytes = bytearray()
            for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1MB 分块
                if chunk:
                    image_bytes.extend(chunk)

        result["image_data"] = bytes(image_bytes)
        result["status"] = "SUCCESS"

    except Exception as e:
        result["error"] = f"Download failed: {e}"

    finally:
        os.environ['http_proxy'] = ''
        os.environ['https_proxy'] = ''

    return result


def robust_download(image_url, max_attempts=3):
    """robust download method"""
    for attempt in range(max_attempts):
        result = download_image(image_url)

        if result.get("status") == "SUCCESS":
            return result

        print(f"第 {attempt+1} 次失败，准备重试...")
        time.sleep(2 ** attempt)

    return result

# python3 -m utils.download

