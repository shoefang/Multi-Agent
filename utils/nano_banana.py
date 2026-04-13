"""调用nano banana"""

import random
import json
import zlib
import requests
import time
import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from PIL import Image
import os
from pathlib import Path


def load_api_keys():
    """从 api_keys.json 文件加载 API keys"""
    try:
        # 获取项目根目录（multi_agent 文件夹的父目录）
        current_dir = Path(__file__).parent.parent
        api_keys_file = current_dir / "api_keys.json"

        if api_keys_file.exists():
            with open(api_keys_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            logging.warning(f"未找到 api_keys.json 文件: {api_keys_file}")
            return {}
    except Exception as e:
        logging.error(f"加载 api_keys.json 失败: {e}")
        return {}

class NanobananaAspectRatio(str, Enum):
    """nanobanana 图像比例枚举"""
    SQUARE = "1:1"      # 1:1 正方形
    LANDSCAPE = "16:9"  # 16:9 横向
    PORTRAIT = "9:16"   # 9:16 纵向
    WIDE = "4:3"        # 4:3 宽屏
    TALL = "3:4"        # 3:4 竖屏


class NanobananaImageSize(str, Enum):
    """nanobanana 图像尺寸枚举"""
    SIZE_4K = "4K"      # 4K 分辨率
    SIZE_2K = "2K"      # 2K 分辨率
    SIZE_1K = "1K"      # 1K 分辨率


class NanobananaImageGenerator:
    """nanobanana 图像生成器类，封装 nanobanana API 调用（带重试机制）"""

    def __init__(
        self,
        api_key: str = None,
        base_url: Optional[str] = None,
        max_retries: int = 200,
        retry_delay: int = 5
    ):
        """初始化 nanobanana 图像生成器

        Args:
            api_key: nanobanana API Key（Bearer Token），默认为
                "sk-UoIZrhCRcfHjhn2WaLaMmZYRSQS2dnnG7jrQ10yLagNX67cE"
                如果为 None，则从 api_keys.json 文件中读取
            base_url: API 基础地址，默认为 nanobanana API 地址
                如果为None，则使用默认地址：
                http://api.dbh.baidu-int.com/v1/models/gemini-3-pro-image-preview
            max_retries: 最大重试次数，默认为 10（因为经常失败）
            retry_delay: 重试延迟时间（秒），默认为 5
        """
        # 如果未提供 api_key，则从 JSON 文件加载
        if api_key is None:
            api_keys = load_api_keys()
            api_key = api_keys.get("nanobanana", {}).get(
                "api_key",
                "sk-UoIZrhCRcfHjhn2WaLaMmZYRSQS2dnnG7jrQ10yLagNX67cE"
            )
        if base_url is None:
            base_url = (
                "http://api.dbh.baidu-int.com/v1/models/"
                "gemini-3-pro-image-preview"
            )
        self.api_key = api_key
        self.base_url = base_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)

    def _get_headers(self) -> Dict[str, str]:
        """生成请求头

        Returns:
            包含认证信息的请求头字典
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def generate(
        self,
        prompt: str,
        image: List = [],
        aspect_ratio: NanobananaAspectRatio = NanobananaAspectRatio.SQUARE,
        image_size: NanobananaImageSize = NanobananaImageSize.SIZE_4K,
        temperature: float = 1.0,
        timeout: int = 360
    ) -> Dict[str, Any]:
        """生成图像（带重试机制）

        Args:
            prompt: 图像生成提示词
            aspect_ratio: 图像比例，默认为 1:1
            image_size: 图像尺寸，默认为 4K
            temperature: 生成温度，默认为 1.0
            timeout: 单次请求超时时间（秒），默认为 180（3分钟）

        Returns:
            包含响应信息的字典，包含以下字段：
                - status_code: HTTP 状态码
                - response: 响应文本
                - json: 解析后的 JSON 数据（如果成功）
                - image_data: Base64 编码的图片数据（如果成功）
                - retry_count: 实际重试次数

        Raises:
            requests.RequestException: 请求异常（达到最大重试次数后）
        """
        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "mediaResolution": "media_resolution_high",
                "temperature": temperature,
                "imageConfig": {
                    "aspectRatio": aspect_ratio.value,
                    "imageSize": image_size.value
                }
            }
        }
        if image:
            for img in image:
                data["contents"][0]["parts"].append({"inline_data": {
                    "mime_type": img["mime"],
                    "data": img["data"]
                }})
        headers = self._get_headers()
        last_exception = None

        for retry_count in range(1, self.max_retries + 1):
            try:
                self.logger.info(
                    "nanobanana 生成请求 (尝试 %d/%d): "
                    "aspect_ratio=%s, image_size=%s",
                    retry_count, self.max_retries,
                    aspect_ratio.value, image_size.value
                )

                response = requests.post(
                    self.base_url,
                    json=data,
                    timeout=timeout,
                    headers=headers
                )

                result = {
                    "status_code": response.status_code,
                    "response": response.text,
                    "retry_count": retry_count
                }

                # 检查 HTTP 状态码
                if response.status_code != 200:
                    error_msg = (
                        f"HTTP {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    self.logger.warning(
                        "nanobanana 请求失败 (尝试 %d/%d): %s",
                        retry_count, self.max_retries, error_msg
                    )
                    if retry_count < self.max_retries:
                        time.sleep(self.retry_delay * int(retry_count))
                        continue
                    else:
                        result["error"] = error_msg
                        return result

                # 尝试解析 JSON 响应
                try:
                    json_data = response.json()
                    result["json"] = json_data

                    # 检查是否有错误
                    if "error" in json_data:
                        error_msg = json_data["error"].get(
                            "message", "Unknown error"
                        )
                        self.logger.warning(
                            "nanobanana API 错误 (尝试 %d/%d): %s",
                            retry_count, self.max_retries, error_msg
                        )
                        if retry_count < self.max_retries:
                            time.sleep(self.retry_delay)
                            continue
                        else:
                            result["error"] = error_msg
                            return result

                    # 提取图片数据
                    if (
                        "candidates" in json_data
                        and len(json_data["candidates"]) > 0
                    ):
                        candidates = json_data["candidates"]
                        for candidate in candidates:
                            content = candidate.get("content", {})
                            parts = content.get("parts", [])
                            for part in parts:
                                if "inlineData" in part:
                                    inline_data = part["inlineData"]
                                    image_data = inline_data.get("data", "")
                                    if image_data:
                                        result["image_data"] = image_data
                                        self.logger.info(
                                            "nanobanana 生成成功 (尝试 %d/%d): "
                                            "图片数据大小 %d bytes",
                                            retry_count, self.max_retries,
                                            len(image_data)
                                        )
                                        return result

                    # 没有找到图片数据
                    self.logger.warning(
                        "nanobanana 响应中未找到图片数据 (尝试 %d/%d)",
                        retry_count, self.max_retries
                    )
                    if retry_count < self.max_retries:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        result["error"] = "未找到图片数据"
                        return result

                except json.JSONDecodeError as e:
                    self.logger.warning(
                        "nanobanana 响应 JSON 解析失败 (尝试 %d/%d): %s",
                        retry_count, self.max_retries, str(e)
                    )
                    if retry_count < self.max_retries:
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        result["error"] = f"JSON 解析失败: {str(e)}"
                        return result

            except requests.RequestException as e:
                last_exception = e
                self.logger.warning(
                    "nanobanana 请求异常 (尝试 %d/%d): %s",
                    retry_count, self.max_retries, str(e)
                )
                if retry_count < self.max_retries:
                    time.sleep(self.retry_delay * int(retry_count))
                    continue
                else:
                    self.logger.error(
                        "nanobanana 请求失败，达到最大重试次数: %s",
                        str(e)
                    )
                    raise

        # 如果所有重试都失败
        if last_exception:
            print(str(last_exception))
            return None

        # 理论上不会到达这里，但为了完整性
        return {
            "status_code": 0,
            "response": "",
            "error": "达到最大重试次数，未成功生成图片",
            "retry_count": self.max_retries
        }


if __name__ == "__main__":
    os.environ['http_proxy'] = ''
    os.environ['https_proxy'] = ''

    img_generator = NanobananaImageGenerator()
    res = img_generator.generate(
        prompt="A cute cat in space, digital art",
    )
    print("res:", res)