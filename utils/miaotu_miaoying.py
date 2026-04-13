#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
妙图、妙影接口
"""

from __future__ import annotations
import os
import io
import sys
import json
import time
import base64
import argparse
from datetime import datetime
from typing import List, Dict, Optional, Any, Iterable
import subprocess
import requests
import zlib
import random
import requests
from PIL import Image, ImageDraw, ImageFont



DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 1280
DEFAULT_BNS = 'group.smartbns-from_product=default%group.flow-gips-access-search.www.all'
# DEFAULT_MIAOYING_ADDR = getip(DEFAULT_BNS)
# DEFAULT_MIAOYING_AK = 'cny_2026_aigc_offline2'
# DEFAULT_MIAOYING_SK = 'cny_2026_aigc_offline2'

DEFAULT_MIAOYING_ADDR = '10.12.75.202:8091'
DEFAULT_MIAOYING_AK = 'test'
DEFAULT_MIAOYING_SK = 'test'

def image_file_to_base64(path: Optional[str]) -> Optional[str]:
    """Return pure base64 string for a local image file, or None if unavailable."""
    if not path:
        return None
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

_MIAOYING_SESSION = requests.Session()


def _miaoying_headers(ak: str, sk: str) -> Dict[str, str]:
    cur_time = int(time.time())
    expire_time = cur_time + 60
    token = str(zlib.crc32((ak + str(cur_time) + sk).encode('utf-8')) & 0xffffffff)
    return {
        "Authorization": f"gips-auth-v1/{ak}/{cur_time}/{expire_time}/{token}",
        "Content-Type": "application/json",
    }

# 调用妙影服务
def _submit_to_miaoying(addr: str, ak: str, sk: str, image_b64: str, prompt: str,
                        model_name: str = 'Shadow-i2v', request_id: Optional[int] = None,
                        need_watermark: Optional[bool] = None, prompt_extend: Optional[int] = None) -> Dict:
    if not addr or not ak or not sk:
        raise ValueError("Miaoying submission requires MIAOYING_ADDR, MIAOYING_AK and MIAOYING_SK")
    if request_id is None:
        request_id = random.randint(10**11, 10**12 - 1)
    payload: Dict[str, object] = {
        "model_name": model_name,
        "image": image_b64,
        "prompt": prompt,
        "request_id": request_id,
    }
    if need_watermark is not None:
        payload["need_watermark"] = bool(need_watermark)
    if prompt_extend is not None:
        payload["prompt_extend"] = prompt_extend
    url = f"http://{addr}/api/v1/videoGenerate"
    headers = _miaoying_headers(ak, sk)
    resp = _MIAOYING_SESSION.post(url, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                headers=headers, timeout=30)
    try:
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Miaoying submit HTTP {resp.status_code}: {resp.text}") from e
    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Miaoying submit returned non-JSON body: {resp.text}") from e

# 下载妙图的图片（妙图的url需要处理后才能下载）
def _download_url_to_file(url: str, out_path: str, session: Optional[requests.Session] = None) -> str:
    sess = session or requests.Session()
    target_url = url
    if "gips" in target_url:
        parts = target_url.split("/")
        if len(parts) > 2:
            original_host = parts[2]
            target_url = target_url.replace(original_host, "yawen-gips.baidu-int.com", 1)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    if Image is not None:
       
        res = sess.get(target_url, timeout=30)
        res.raise_for_status()
        img = Image.open(io.BytesIO(res.content)).convert("RGB")
        img.save(out_path, format='JPEG', quality=95)
        return out_path

    with sess.get(target_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)
    return out_path



# 通过妙图生成图片
def I2I_with_miaotu(prompt, image_urls, image_ratio='16:9', save_path=None):
    """
    通过妙图生成图片
    """
    AK = DEFAULT_MIAOYING_AK
    SK = DEFAULT_MIAOYING_SK
    def get_tk(cur_time, AK, SK):
        TS = cur_time
        combined_str = AK + str(TS) + SK
        combined_bytes = combined_str.encode('utf-8')  # 使用UTF-8编码转换为字节串
        # 计算CRC32并确保结果是32位无符号整数
        TK = str(zlib.crc32(combined_bytes) & 0xffffffff) 
        return TK
    
    try:

        # 构造请求数据
       
        image_quality = "middle"
        addr = DEFAULT_MIAOYING_ADDR
        logid = random.randint(111111111111, 666666666666)
        
        data = {
            "prompt": prompt,
            "image_arr_url": image_urls,
            "image_ratio": image_ratio, #不传默认"1:1" 只可选 "1:1", "16:9", "9:16", "4:3", "3:4"
            "image_quality": image_quality, #分辨率选择，不传默认"middle" 标清：“middle” 高清：high”
            "prompt_extend": 0,
            "request_id": logid
        }

        data = json.dumps(data, ensure_ascii=True)
        print(data)
        url = 'http://{}/api/v2/imageEdit'.format(addr)
        cur_time = int(time.time())
        expire_time = cur_time + 60
        headers = {
                    "Authorization": f"gips-auth-v1/{AK}/{cur_time}/{expire_time}/{get_tk(cur_time, AK, SK)}",
                    "Content-Type": "application/json"
                }
        os.environ["https_proxy"] = ""
        res = requests.post(url, data, timeout=60, headers=headers)

        if res:
            response_data = res.json()
            url = response_data['data']['result'][0]['img_url']
            return url
    except Exception as e:
        raise Exception(e)


# 下载视频
def download_video(url, save_path):
    """
    下载视频
    """
    for i in range(10):

        try:
            response = requests.get(url, stream=True, verify=False)

            if response.status_code == 200:
                # 打开文件以二进制写入方式保存视频
                with open(save_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)

                return True
            else:

                raise Exception("请求失败")
        except Exception as e:
            time.sleep(i + 5)

# 根据 task_id 查询视频生成进度
def get_task_creations(task_id):
    """
    根据 task_id 查询视频生成进度
    """
    AK = DEFAULT_MIAOYING_AK
    SK = DEFAULT_MIAOYING_SK
    ADDR = DEFAULT_MIAOYING_ADDR

    def get_tk(ts):
        return str(zlib.crc32((AK + str(ts) + SK).encode('utf-8')) & 0xffffffff)
    

    url = f'http://{ADDR}/api/v1/videoGenerateQuery'
    payload = {'task_id': task_id, 'request_id': random.randint(10 ** 11, 10 ** 12 - 1)}
    cur = int(time.time())
    expire = cur + 60
    headers = {
        'Authorization': f'gips-auth-v1/{AK}/{cur}/{expire}/{get_tk(cur)}',
        'Content-Type': 'application/json'
    }
    r = requests.post(url, json=payload, timeout=30, headers=headers)
    r.raise_for_status()
    return r.json()

def generate_image_with_miaotu(prompt: str,
                            save_path: str = None,
                            width: int = DEFAULT_WIDTH,
                            height: int = DEFAULT_HEIGHT) -> str:
    """
    通过妙图生成图片
    """
    AK = DEFAULT_MIAOYING_AK
    SK = DEFAULT_MIAOYING_SK
    def get_tk(cur_time, AK, SK):
        TS = cur_time
        combined_str = AK + str(TS) + SK
        combined_bytes = combined_str.encode('utf-8')  # 使用UTF-8编码转换为字节串
        # 计算CRC32并确保结果是32位无符号整数
        TK = str(zlib.crc32(combined_bytes) & 0xffffffff) 
        return TK
    
    try:

        # 构造请求数据
        image_ratio = "16:9"
        image_quality = "middle"
        addr = '10.150.130.34:8000'
        logid = random.randint(111111111111, 666666666666)
        data = {
            "prompt": prompt,
            "image_ratio": image_ratio, #不传默认"1:1" 只可选 "1:1", "16:9", "9:16", "4:3", "3:4"
            "image_quality": image_quality, #分辨率选择，不传默认"middle" 标清：“middle” 高清：high”
            "prompt_extend": 0,
            "request_id": logid
        }

        data = json.dumps(data, ensure_ascii=True)
        url = 'http://{}/api/v2/imagecreate'.format(addr)
        cur_time = int(time.time())
        expire_time = cur_time + 60
        headers = {
                "Authorization": f"gips-auth-v1/{AK}/{cur_time}/{expire_time}/{get_tk(cur_time, AK, SK)}",
                "Content-Type": "application/json"
            }
        
        # 发起请求
        resp = requests.post(url, data, timeout=15, headers=headers)
        if resp:
            response_data = resp.json()

            url = response_data['data']['result'][0]['img_url']
            if save_path is not None:
                _download_url_to_file(url, save_path)
            return url
        else:
            raise Exception("调用妙图响应为空")
    except Exception as e:

        raise Exception(e)
    
def gen_video_with_miaoying(prompt, first_frame__path, video_save_path):
    """
    通过妙影生成视频
    """
    base64_image = image_file_to_base64(first_frame__path)
    submit_resp = _submit_to_miaoying(
        addr=DEFAULT_MIAOYING_ADDR,
        ak=DEFAULT_MIAOYING_AK,
        sk=DEFAULT_MIAOYING_SK,
        image_b64=base64_image,
        prompt=prompt,
        model_name='Shadow-i2v',
        request_id=None,
        need_watermark=None,
        prompt_extend=0,
    )
    task_id = (submit_resp.get('data') or {}).get('task_id')

    # 轮询查询任务，判断是否结束
    start_time = time.time()
    timeout = 1000
    while time.time() - start_time < timeout:
        response_data = get_task_creations(task_id)

        if response_data is None:
            break

        status = response_data["data"]["status"]


        if status != "SUCCESS":
            time.sleep(20)
        else:
            url = response_data["data"]["video_url"]

            download_video(url, video_save_path)

            # 计算总耗时并转换为分钟格式
            total_seconds = time.time() - start_time
            total_minutes = total_seconds / 60
            return

    # 如果超时退出循环
    total_seconds = time.time() - start_time
    total_minutes = total_seconds / 60



def process(img_prompt, video_prompt, img_save_path, video_save_path):
    """
    首帧图生成视频
    """
    # 生成首帧图
    generate_image_with_miaotu(img_prompt, img_save_path)

    
    # 生成视频
    # img_save_path = "/Users/lihuining01/Desktop/广告视频/1029_ad_video2/images_save/妙图2.png"
    gen_video_with_miaoying(video_prompt, img_save_path, video_save_path)

if __name__ == '__main__':
    # 生成首帧图
    image_path = ["/home/data/1029_ad_video2/asset/阿迪达斯阿根廷国家足球队训练夹克.png", "/home/data/1029_ad_video2/asset/labubu.jpg"]
    img_prompt = "生长在田野里的葡萄"
    img_save_path = "/home/data/1029_ad_video2/test/妙图.png"
    generate_image_with_miaotu(img_prompt, img_save_path)
    print(I2I_with_miaotu(img_prompt, image_path, img_save_path))
    print(f"首帧图生成成功，保存地址:{img_save_path}")
    
    
    # 生成视频
    # video_save_path = "/home/data/1029_ad_video2/output/妙影视频.mp4"
    # video_prompt = "一位25到30岁的年轻女性，穿着优雅，锁骨处佩戴着挂坠，镜头略微仰拍，展现她的自信微笑，背景是阳光洒进的咖啡馆，画面温暖明亮。"
    # img_save_path = "/home/data/1029_ad_video2/output/妙图.png"
    # gen_video_with_miaoying(video_prompt, img_save_path, video_save_path)