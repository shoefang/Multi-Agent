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
import json


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
    for attempt in range(max_attempts):
        result = download_image(image_url)

        if result.get("status") == "SUCCESS" and result.get("image_data", None) is not None:
            return result
            
        print(f"第 {attempt+1} 次失败，准备重试...")
        time.sleep(2 ** attempt)

    return result


def encode_image_to_base64(image_path):
    """
    将本地图片文件编码为Base64格式
    
    Args:
        image_path (str): 图片文件路径
        
    Returns:
        str: Base64编码的图片数据，格式为 data:image/<格式>;base64,<编码>
    """
    try:
        # 检查文件是否存在
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        # 获取文件扩展名来确定图片格式
        file_extension = Path(image_path).suffix.lower()
        if file_extension not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            raise ValueError(f"不支持的图片格式: {file_extension}")
        
        # 读取图片文件并编码为Base64
        with open(image_path, 'rb') as image_file:
            image_data = image_file.read()
            base64_encoded = base64.b64encode(image_data).decode('utf-8')
        
        # 确定MIME类型
        mime_type_map = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg', 
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp'
        }
        
        mime_type = mime_type_map[file_extension]
        
        # 返回完整的Base64数据URI
        # return {
        #     "mime": mime_type,
        #     "data": base64_encoded
        # }
        return base64_encoded
        
    except Exception as e:
        print(f"❌ 图片编码失败: {e}")
        return None

def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")

class GeminiVodImageGenerator:
    """Gemini VOD 图像生成器 (同步版)
    封装了 BCE 签名、任务提交、状态轮询和图片下载。
    """

    SUBMIT_URI = "/v2/aigc/image"
    TASK_STATUS_URI = "/v2/tasks/{task_id}"

    def __init__(
        self,
        ak: str = None,
        sk: str = None,
        host: str = "vod.bj.baidubce.com",
        max_retries: int = 3,
        poll_interval: int = 5,
        poll_timeout: int = 600
    ):
        """
        Args:
            ak: 百度云 Access Key（如果为 None，则从 api_keys.json 读取）
            sk: 百度云 Secret Key（如果为 None，则从 api_keys.json 读取）
            host: VOD 服务地址
            max_retries: 提交任务失败时的重试次数
            poll_interval: 轮询间隔(秒)
            poll_timeout: 整个任务的最长等待时间(秒)
        """
        # 如果未提供 ak/sk，则从 JSON 文件加载
        if ak is None or sk is None:
            api_keys = load_api_keys()
            vod_config = api_keys.get("vod", {})
            if ak is None:
                ak = vod_config.get("ak", "")
            if sk is None:
                sk = vod_config.get("sk", "")

        self.ak = ak
        self.sk = sk
        self.host = host
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.logger = logging.getLogger(__name__)

    def _generate_bce_authorization(self, method: str, uri: str, timestamp: str) -> str:
        """生成 BCE API 签名"""
        auth_version = "bce-auth-v1"
        expiration_in_seconds = 1800
        signed_headers = "host;x-bce-date"

        # Canonical Request
        timestamp_encoded = quote(timestamp, safe="")
        canonical_headers = f"host:{self.host}\nx-bce-date:{timestamp_encoded}"
        canonical_request = f"{method}\n{uri}\n\n{canonical_headers}"

        # Signing Key
        auth_string_prefix = f"{auth_version}/{self.ak}/{timestamp}/{expiration_in_seconds}"
        signing_key = hmac.new(self.sk.encode(), auth_string_prefix.encode(), hashlib.sha256).hexdigest()

        # Signature
        signature = hmac.new(signing_key.encode(), canonical_request.encode(), hashlib.sha256).hexdigest()

        return f"{auth_version}/{self.ak}/{timestamp}/{expiration_in_seconds}/{signed_headers}/{signature}"

    def _build_headers(self, method: str, uri: str) -> dict:
        """构建包含签名的请求头"""
        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "host": self.host,
            "accept": "*/*",
            "content-type": "application/json",
            "x-bce-request-id": str(uuid.uuid4()),
            "x-bce-date": timestamp,
            "authorization": self._generate_bce_authorization(method, uri, timestamp),
        }

    def generate(self, 
        prompt: str = '', 
        image: List = [],
        aspect_ratio: str = "1:1",
        return_url: bool = False) -> Dict[str, Any]:
        """
        生成图像 (同步阻塞模式)
        包含：提交 -> 轮询 -> 下载
        Args:
            image: 图像列表（Base64）
            prompt: 文本提示
            aspect_ratio: 宽高比

        Returns:
            包含图像数据的字典
        """
        result = {
            "status": "FAILED",
            "image_data": None,
            "error": None,
            "task_id": None
        }
        content = [{
            "type": "text",
            "text": prompt}]
        if image:
            for img in image:
                # content.append(
                #     {
                #         "type": "image_url",
                #         "image_item": {
                #             "image_url": img
                #         }
                #     }
                # )
                if is_url(img):
                    content.append(
                        {
                            "type": "image_url",
                            "image_item": {
                                "image_url": img
                            }
                        }
                    )
                else:
                    content.append(
                        {
                            "type": "image_base64",
                            "image_item": {
                                "image_base64": img
                            }
                        }
                    )


        # --- 步骤 1: 提交任务 ---
        submit_url = f"https://{self.host}{self.SUBMIT_URI}"
        payload = {
            "model": "NBP",  # NBP, NB2
            "messages": [{"role": "user", "content": content}],
            "n": 1, # 生成图片数
            "size": aspect_ratio,
            "quality": "2K",
        }

        task_id = None
        for attempt in range(self.max_retries):
            try:
                headers = self._build_headers("POST", self.SUBMIT_URI)
                resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                resp_json = resp.json()
                print("status_code:", resp.status_code)
                print("response text:", resp.text)
                
                if "code" in resp_json:
                    raise RuntimeError(f"API Error: {resp_json.get('message')}")
                
                task_id = resp_json.get("taskId")
                if task_id:
                    break
            except Exception as e:
                self.logger.warning(f"提交任务失败 (尝试 {attempt+1}/{self.max_retries}): {e}")
                time.sleep(2 ** attempt)

        if not task_id:
            result["error"] = "Failed to submit task after retries"
            return result

        result["task_id"] = task_id
        self.logger.info(f"任务提交成功, TaskID: {task_id}, 开始轮询...")

        # --- 步骤 2: 轮询状态 ---
        start_time = time.time()
        image_url = None
        
        while time.time() - start_time < self.poll_timeout:
            try:
                uri = self.TASK_STATUS_URI.format(task_id=task_id)
                status_url = f"https://{self.host}{uri}"
                headers = self._build_headers("GET", uri)
                
                resp = requests.get(status_url, headers=headers, timeout=30)
                resp.raise_for_status()
                status_data = resp.json()
                
                status = status_data.get("status")
                if status == "SUCCESS":
                    # 解析层级深处的 URL
                    try:
                        info = status_data["videoGenerateTaskInfo"]["videoGenerateTaskOutput"]["mediaBasicInfos"][0]
                        image_url = info["source"]["sourceUrl"]
                        break
                    except (KeyError, IndexError):
                        result["error"] = "Succeeded but no URL found in response"
                        return result
                
                elif status == "FAILED":
                    print(f"轮询图片生成，状态是FAILED。原始响应:{resp.text}")
                    error_msg = status_data.get("videoGenerateTaskInfo", {}).get("error", "Unknown error")
                    result["error"] = f"Task failed: {error_msg}"
                    return result
                
                self.logger.debug(f"任务 {task_id} 状态: {status}, 等待 {self.poll_interval}s...")
                time.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"轮询出错: {e}")
                time.sleep(self.poll_interval)

        if not image_url:
            result["error"] = "Polling timeout"
            return result

        # image_url = "https://fjvtnkc2myqwvqknz8h7.exp.bcevod.com/mda-gccwc11biatvt2a5/_src/mda-gccwc11biatvt2a5/gccw3e7jhmd5b5s40inn.png"
        print("image_url:", image_url)
        result["image_url"] = image_url
        if return_url:
            return f"生成的图片url是:{image_url}"
        # --- 步骤 3: 下载图片 ---
        try:
            os.environ['http_proxy'] = 'http://agent.baidu.com:8891'
            os.environ['https_proxy'] = 'http://agent.baidu.com:8891'
            self.logger.info(f"正在从 URL 下载图片...")
            # img_resp = requests.get(image_url, timeout=60)
            # img_resp.raise_for_status()
            # result["image_data"] = img_resp.content # 原始图片二进制 bytes

            result["image_data"] = robust_download(image_url)["image_data"]

            result["status"] = "SUCCESS"
            os.environ['http_proxy'] = ''
            os.environ['https_proxy'] = ''
            return result
        except Exception as e:
            result["error"] = f"Download failed: {e}"
            return result


def download_with_retry(url, max_retries=3, timeout=60):
    session = requests.Session()

    retry = Retry(
        total=max_retries,
        backoff_factor=1,  # 1秒递增
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()

    if not resp.content:
        raise ValueError("Downloaded image is empty")

    if "image" not in resp.headers.get("Content-Type", ""):
        raise ValueError("Response is not an image")

    return resp.content

# python3 -m utils.nano_banana_vod
# --- 调用示例 ---
if __name__ == "__main__":
    # start_time = time.time()
    # image_url = "https://fjvtnkc2myqwvqknz8h7.exp.bcevod.com/mda-gcdruav1mbvwkiym/_src/mda-gcdruav1mbvwkiym/gcdrs9ggtj0ffrnqxxsh.png"

    # result = robust_download(image_url)
    # print("result type:", type(result))
    # end_time = time.time()
    # print("total cost time:", end_time - start_time)

    # exit()
    # os.environ['http_proxy'] = 'http://agent.baidu.com:8891'
    # os.environ['https_proxy'] = 'http://agent.baidu.com:8891'

    # content = download_with_retry(image_url)
    # print("content type:", type(content))
    # exit()

    # image_url = "https://fjvtnkc2myqwvqknz8h7.exp.bcevod.com/mda-gccwc11biatvt2a5/_src/mda-gccwc11biatvt2a5/gccw3e7jhmd5b5s40inn.png"
    # os.environ['http_proxy'] = 'http://agent.baidu.com:8891'
    # os.environ['https_proxy'] = 'http://agent.baidu.com:8891'

    # img_resp = requests.get(image_url, timeout=60)
    # print("download status:", img_resp.status_code)
    # print("content-type:", img_resp.headers.get("Content-Type"))
    # print("python type:", type(img_resp.content))
    # print("length:", len(img_resp.content))
    # print("first 20 bytes:", img_resp.content[:20])
    # exit()
    start_time = time.time()
    # os.environ['http_proxy'] = 'http://agent.baidu.com:8891'
    # os.environ['https_proxy'] = 'http://agent.baidu.com:8891'
    template_path = "./template/grid_1_1.png"
    img = Image.open(template_path)
    img_url = "http://miaobi-general-product.bj.bcebos.com/b%27v0MDKMvHZox36wuZ01jj4w%3D%3D%27.png?authorization=bce-auth-v1%2FALTAKmda7zOvhZVbRzBLewvCMU%2F2026-03-04T09%3A22%3A23Z%2F-1%2F%2F9969789467b23ca473afff0a373e654045442fae9523996d0251a555d07bb781"
    # img_url = upload_image(img)
    #img_url = encode_image_to_base64(template_path)
    logging.basicConfig(level=logging.INFO)
    test_prompt = """
### 网格位置 1  \n宽高比：1:1  \n标题：恢复成本  \n类型：Recovery Cost  \n\n画面呈现要求：  \n1. 必须完整显示以下文本内容：  \n   - Headline: **恢复成本**  \n   - Body:  \n     - 拉黑：一键解除  \n     - 删除：需重新关注  \n\n2. 视觉对比设计：  \n   - 左侧区域：单按钮「解除」设计  \n   - 右侧区域：多步骤流程图（标注「搜索→关注」流程）  \n\n3. 布局结构：  \n   - 采用「Step Flow vs Single Action」对比式布局  \n   - 严格保持左右分区的画面比例
    """
    
    # 初始化
    generator = GeminiVodImageGenerator(
        ak="",
        sk="",
        host="vod.bj.baidubce.com"
    )
    final_res = {}
    for i in range(1):
        # 同步调用，就像 nano-banana 一样
        res = generator.generate(
            prompt= test_prompt,
            image = [img_url]
        )
        final_res[i] = res["image_url"]
        generate_time = time.time()
        print("generate cost time:", generate_time - start_time)

    print("final_res:", final_res)
    # results_file = '0305-gemini-pro-vod-case.json'
    # with open(results_file, "w") as f:
    #     f.write(json.dumps(final_res, ensure_ascii=False, indent=True))
    # if res["status"] == "SUCCESS":
    #     with open("/home/work/data/lhn/0302/code_信息图/exp/0305/原始prompt.jpg", "wb") as f:
    #         f.write(res["image_data"])
    #     print("图片生成成功！")
    # else:
    #     print(f"生成失败: {res['error']}")
    # end_time = time.time()
    # print("total cost time:", end_time - start_time)
