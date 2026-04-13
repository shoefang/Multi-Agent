#coding=utf-8
"""
large model api 
"""
import json
import logging
import base64
from typing import Any, Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
from pathlib import Path
import re

import io
from PIL import Image


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


def request_llm_v2(prompt, system_prompt=None, model_name="deepseek-v3", messages=None, tools=None, temperature=0.2):
    """
    调用千帆大语言模型
    """
    url = "https://qianfan.baidubce.com/v2/chat/completions"
    # 从 JSON 文件加载 API key
    api_keys = load_api_keys()
    qianfan_api_key = api_keys.get("qianfan", {}).get("api_key", "bce-v3/ALTAK-5lwRoR8JCyc0ek3F3VWhZ/6b7a7d1c9e903071862b85dcb23739e981a2f678")

    headers = {
        'Content-Type': 'application/json',
        'appid': 'app-ZFENiJvw',
        "Authorization": f"Bearer {qianfan_api_key}"
    }
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    if not messages and not prompt:
        return None
        
    if not messages:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 16384,
        "web_search": {
            "enable": False,
            "enable_citation": False,
            "enable_trace": False
        }
    }
    if tools:
        payload["tools"] = tools

    try:
        response = session.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        response.raise_for_status()
        ret = response.json()
        if 'choices' in ret and ret['choices']:
            return ret
        else:
            logging.error("Invalid response structure: %s", ret)
            return ""
    except requests.exceptions.RequestException as e:
        logging.error("Request error: %s", e)
        return ""   

def request_llm(prompt, system_prompt=None, model_name="deepseek-v3", messages=None, temperature=0.2):
    """
    调用千帆大语言模型
    """
    url = "https://qianfan.baidubce.com/v2/chat/completions"
    # 从 JSON 文件加载 API key
    api_keys = load_api_keys()
    qianfan_api_key = api_keys.get("qianfan", {}).get("api_key", "bce-v3/ALTAK-5lwRoR8JCyc0ek3F3VWhZ/6b7a7d1c9e903071862b85dcb23739e981a2f678")

    headers = {
        'Content-Type': 'application/json',
        'appid': 'app-ZFENiJvw',
        "Authorization": f"Bearer {qianfan_api_key}"
    }
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    if not messages and not prompt:
        return None
        
    if not messages:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 16384,
        "web_search": {
            "enable": False,
            "enable_citation": False,
            "enable_trace": False
        }
    }
    try:
        response = session.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        response.raise_for_status()
        ret = response.json()
        if 'choices' in ret and ret['choices']:
            result_content = ret['choices'][0]['message']['content']
            try:
                reasoning_content = ret['choices'][0]['message']['reasoning_content']
            except KeyError:
                reasoning_content = ""
            return result_content
        else:
            logging.error("Invalid response structure: %s", ret)
            return ""
    except requests.exceptions.RequestException as e:
        logging.error("Request error: %s", e)
        return ""   


def parse_json(raw_str):
    """
        解析JSON格式的字符串，并返回一个Python对象。
    如果字符串不是以```json开头或者结尾，则会被剪切。

    Args:
        raw_str (str): JSON格式的字符串，可能包含前后的 ```json 和 ``` 标记。

    Returns:
        dict: 解析后得到的Python字典对象。

    Raises:
        None.
    """
    if not raw_str:
        return None

    # 首先尝试 ```json 包裹的格式
    match = re.search(r"```json\s*(.*?)\s*```", raw_str, re.S)
    if match:
        clean = match.group(1).strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass
    
    # 如果没有找到，尝试找到任何JSON对象（以{开头}结尾）
    json_match = re.search(r'\{.*\}', raw_str, re.S)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    
    # 最后尝试直接解析整个字符串
    try:
        return json.loads(raw_str.strip())
    except Exception as e:
        print(e)
        return None


def pil_image_to_base64(image, format="JPG"):
    """
    将 PIL Image 对象直接转换为 Base64 字符串
    """
    if image is None:
        return None
    
    try:
        # 1. 创建内存缓冲区
        buffered = io.BytesIO()
        # 2. 将图片保存到缓冲区（而不是硬盘）
        image.save(buffered, format=format)
        # 3. 获取字节流并编码
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        # 4. 拼接成 Data URI 格式（符合你之前的函数风格）
        mime_type = f"image/{format.lower()}"
        if format.lower() == "jpg": 
            mime_type = "image/jpeg"
        
        return f"data:{mime_type};base64,{img_str}"
    except Exception as e:
        print(f"❌ PIL转Base64失败: {e}")
        return None


def generate_image_with_doubao(
    prompt,
    image_paths=None,
    model="doubao-seedream-4-0-250828",
    size="2K",
    api_key=None,
    sequential_image_generation="disabled",
    max_images=None,
    stream=False,
    response_format="url",
    watermark=True
):
    """
    使用豆包API生成图片
    
    Args:
        prompt (str): 图片生成提示词
        image_paths (str/list, optional): 本地图片路径，可以是单个路径字符串或路径列表
        model (str): 使用的模型，默认为 "doubao-seedream-4-0-250828"
        size (str): 图片尺寸，如 "2K", "1440x2560" 等
        api_key (str): API密钥，如果为None则使用默认值
        sequential_image_generation (str): 序列图片生成模式，"disabled", "auto" 等
        max_images (int, optional): 最大生成图片数量，当sequential_image_generation为"auto"时使用
        stream (bool): 是否流式返回
        response_format (str): 响应格式，"url" 或 "b64_json"
        watermark (bool): 是否添加水印
        
    Returns:
        dict: API响应结果，包含生成的图片信息
    """
    # API配置
    url = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    proxies = {
    "http": "http://agent.baidu.com:8891",
    "https": "http://agent.baidu.com:8891",
    }
    if image_paths is None:
        image_paths = []
    # 使用传入的API密钥或从JSON文件加载
    if api_key is None:
        api_keys = load_api_keys()
        api_key = api_keys.get("doubao", {}).get("api_key", "7862f9a7-5ae3-4072-a6ca-58d06efff85c")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    # 构建请求数据
    data = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "sequential_image_generation": sequential_image_generation,
        "stream": stream,
        "response_format": response_format,
        "watermark": False,
        "image": image_paths
    }
    
    # 处理序列图片生成选项
    if sequential_image_generation == "auto" and max_images is not None:
        data["sequential_image_generation_options"] = {
            "max_images": max_images
        }
    
    try:
        print("📤 发送请求到豆包API...")
        response = requests.post(url, headers=headers, json=data, proxies=proxies)
        
        if response.status_code == 200:
            print("✅ 请求成功！")
            print(response.json())
            return response.json()
        else:
            print(f"❌ 请求失败: {response.status_code}")
            return {
                "error": f"API请求失败",
                "status_code": response.status_code,
                "response": response.text
            }
            
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return {"error": f"请求异常: {e}"}



if __name__ == "__main__":
    input = "/home/data/icode/shangdan/output-lj/result.json"
    output = "/home/data/icode/shangdan/output-lj/final_result.json"
    with open(input, "r") as f:
        data = json.load(f)
    

    res=[]
    for i in range(len(data)):
        prompt = f"""
        我给你一组图片描述，这组图是客户给我让我用来生产软广图文的，你的任务：
    1. 请你仔细阅读每张图的描述，对其进行关联性阅读，理解用户为什么要上传这几张，要表达什么；
    2. 每张图都给我返回一个**一句话描述**，方便我理解这个图想传达什么核心，方便我后续写文章；

    返回以字典格式，key为图片url，values为一句话描述。

    【输出格式】
    {{
    "image1": "这是一个描述",
    "image2": "这是一个描述",
    }}
        
    【图像描述】
    {data[i]}
        
        """


        result = request_llm_v2(prompt=prompt)
        result = parse_json(result['choices'][0]['message']['content'])
        res.append(result)
    
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=4)