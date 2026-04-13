#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
 Copyright (c) 2025 Baidu.com, Inc. All Rights Reserved
"""

import requests
import json
import time

# -*- coding: utf-8 -*-
"""
put bos
pip install baidubce==0.8.3 bce-python-sdk==0.9.10
"""
from baidubce.utils import get_md5_from_fp
from baidubce.services.bos.bos_client import BosClient
from baidubce.bce_client_configuration import BceClientConfiguration
from baidubce.auth.bce_credentials import BceCredentials
from io import BytesIO
import os
import json
from pathlib import Path

import pandas as pd
from typing import DefaultDict, List
import ast


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
            import logging
            logging.warning(f"未找到 api_keys.json 文件: {api_keys_file}")
            return {}
    except Exception as e:
        import logging
        logging.error(f"加载 api_keys.json 失败: {e}")
        return {}


# 从 JSON 文件加载 BOS 配置
api_keys = load_api_keys()
bos_config = api_keys.get("bos_general", {})

bos_host = "http://miaobi-general-product.bj.bcebos.com"
access_key_id = bos_config.get("access_key_id", "")
secret_access_key = bos_config.get("secret_access_key", "")
bucket_name = bos_config.get("bucket_name", "miaobi-general-product")

config = BceClientConfiguration(credentials=BceCredentials(access_key_id, secret_access_key), endpoint=bos_host)
bos_client = BosClient(config)
# bucket_name = "miaobi-auto-layout"
 
def upload_image(image, name=None):
    """
    上传图片到BOS，返回图片的预签名URL。
    
    Args:
        image (Image.Image): 待上传的图片，需为PIL格式。
        name (str): BOS中图片的名称。
    
    Returns:
        str: 图片的预签名URL，可用于下载和展示。
    
    Raises:
        None.
    """
    bytes_io = BytesIO()
    image.save(bytes_io, format='PNG')
    bytes_io.seek(0)
 
    content_md5 = get_md5_from_fp(bytes_io, buf_size=bos_client.config.recv_buf_size)
    content_length = bytes_io.getbuffer().nbytes
    if name is None:
        name = "%s.png" % content_md5
 
    bos_client.put_object(bucket_name, name, bytes_io, content_length, content_md5, content_type='image/png')
    url = bos_client.generate_pre_signed_url(bucket_name, name, expiration_in_seconds=-1).decode()
 
    return url

def upload_json(data, name=None):
    """
    上传JSON格式的数据到BOS，返回JSON的预签名URL。
    """
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False)
    
    bytes_io = BytesIO(data.encode('utf-8'))
    bytes_io.seek(0)
     
    content_md5 = get_md5_from_fp(bytes_io, buf_size=bos_client.config.recv_buf_size)
    content_length = bytes_io.getbuffer().nbytes
    if name is None:
        name = "%s.json" % content_md5
    
    bos_client.put_object(bucket_name, name, bytes_io, content_length, content_md5, content_type='application/json')
    url = bos_client.generate_pre_signed_url(bucket_name, name, expiration_in_seconds=-1).decode()

    return url


def parse_json(content):
    """
    解析JSON格式的字符串，并返回一个Python对象。
    如果字符串不是以```json开头或者结尾，则会被剪切。

    Args:
        content (str): JSON格式的字符串，可能包含前后的 ```json 和 ``` 标记。

    Returns:
        dict: 解析后得到的Python字典对象。

    Raises:
        None.
    """
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.replace("'", '“').replace("\n", "")
    try:
        return json.loads(content)

    except Exception as e:
        print(e)
        # logs.warning(f"""parse_json err: {content}""")
        return {}


def request_vlm(
    input_prompt,
    image_url,
    model="qwen2.5-vl-7b-instruct",
    APP_ID='app-CdxzgKFY', 
    API_KEY='Bearer bce-v3/ALTAK-KmUVUm1imukLo7Z1wsmKg/0a78674da950c10655e2c519425f79ff86668267'
    ):

    """
    请求VLM模型生成响应
    """
    
    url = "https://qianfan.baidubce.com/v2/chat/completions"
    content = [{"type": "text", "text": input_prompt}, {"type": "image_url", "image_url": {"url": image_url}}]
    payload = json.dumps({
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ]
    })
    headers = {
        'Content-Type': 'application/json',
        'appid': APP_ID,
        'Authorization': API_KEY
    
    }
    for i in range(3):
        try:
            response = requests.request("POST", url, headers=headers, data=payload)

            #print("response.text", type(response.text), response.text)
            res = json.loads(response.text)["choices"][0]["message"]["content"]
            res = parse_json(res)
            return res
        except Exception as e:
            print(e)
            time.sleep(2)
            continue
    return {}

def image_understanding(
    image_url,
    brief='',
    model="qwen3-vl-32b-instruct",
    APP_ID='app-CdxzgKFY', 
    API_KEY='Bearer bce-v3/ALTAK-KmUVUm1imukLo7Z1wsmKg/0a78674da950c10655e2c519425f79ff86668267' 
    ):

    """
    请求VLM模型进行图像理解
    """

    input_prompt = f"""
    【角色设定】
    你是一位专业的图像分析专家和资深撰稿人，擅长捕捉图像中的视觉细节、情感氛围以及产品名称。禁止输出任何 Markdown 标记（如 ```json），禁止输出任何开场白、思考过程、草稿或结束语。
    
    【任务目标】
    请你结合用户上传的信息，分析上传的这组图像，并为每张图片提供详细的说明（Caption）。

    【描述要求】
    视觉细节：涵盖主体、动作、环境背景。
    文本信息：如果图像中包含关键文字或标志（Logo），请准确提取。

    【输出注意事项】：
    1. 只输出JSON格式的数据，不要包含任何其他文字
    2. 确保所有字符串使用双引号
    3. 确保JSON格式完整且有效
    4. 严格按照输出格式输出，不要输出任何多余的内容！

    【输出格式】
    [
        {{'url':image1, 'desc':描述1}},
        {{'url':image2, 'desc':描述2}},
        ...
    ]

    【用户上传信息】
    {brief}
    """
    
    url = "https://qianfan.baidubce.com/v2/chat/completions"
    content = [{"type": "text", "text": input_prompt}]
    if type(image_url) == str:
        image_url = parse_json(image_url)
    content.extend([{"type": "image_url", "image_url": {"url": url}} for url in image_url])
    payload = json.dumps({
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ],
        "temperature": 0.2
    })
    headers = {
        'Content-Type': 'application/json',
        'appid': APP_ID,
        'Authorization': API_KEY
    
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    res = json.loads(response.text)["choices"][0]["message"]["content"]
    res = parse_json(res)
    return res
    
    

    
if __name__ == "__main__":

    
    input_path = "/home/data/icode/baidu/miaobi/multi_agent/inputs/2026电影推荐.json"
    with open(input_path, "r") as f:
        data = json.load(f)
    images = data['images']
    image_list = []
    for key, value in images.items():
        image_list.append(value)
    user_input = f"""
    [query] 
    {data['query']}
    [requirements]
    {data['requirements']}
    """ 
    task_tpye = data['task_type']
    save_dir = "/home/data/icode/baidu/miaobi/multi_agent/inputs/2026电影推荐_理解.json"
    print(image_understanding(image_list, brief=user_input))
    

