# -*- coding: utf-8 -*-
"""
test bos
"""
from baidubce.utils import get_md5_from_fp
from baidubce.services.bos.bos_client import BosClient
from baidubce.bce_client_configuration import BceClientConfiguration
from baidubce.auth.bce_credentials import BceCredentials
from PIL import Image
from io import BytesIO
import os
import cv2
from pathlib import Path
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
            import logging
            logging.warning(f"未找到 api_keys.json 文件: {api_keys_file}")
            return {}
    except Exception as e:
        import logging
        logging.error(f"加载 api_keys.json 失败: {e}")
        return {}


# bos_host = "http://miaobi-auto-layout.bj.bcebos.com"
# access_key_id = ""
# secret_access_key = ""
bos_host = "bucket name: miaobi-pro-video-news"
bos_host = "http://miaobi-pro-video-news.bj.bcebos.com"

# 从 JSON 文件加载 BOS 配置
api_keys = load_api_keys()
bos_config = api_keys.get("bos_video", {})

access_key_id = bos_config.get("access_key_id", "")
secret_access_key = bos_config.get("secret_access_key", "")
bucket_name = bos_config.get("bucket_name", "miaobi-pro-video-news")

config = BceClientConfiguration(credentials=BceCredentials(access_key_id, secret_access_key), endpoint=bos_host)
bos_client = BosClient(config)
# bucket_name = "miaobi-auto-layout"
 
def upload_bos_image(image, name=None):
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
 
 
def upload_video_to_bos(video_path, name=None):
    """
    上传视频到BOS，返回视频的预签名URL。
    
    Args:
        video_path (str): 待上传的视频文件路径。
        name (str): BOS中视频的名称。
    
    Returns:
        str: 视频的预签名URL，可用于下载和展示。
    
    Raises:
        None.
    """
    # 以二进制方式读取视频文件
    with open(video_path, 'rb') as video_file:
        bytes_io = BytesIO(video_file.read())
 
    # 计算MD5和内容长度
    content_md5 = get_md5_from_fp(bytes_io, buf_size=bos_client.config.recv_buf_size)
    content_length = bytes_io.getbuffer().nbytes
 
    # 如果没有指定文件名，使用MD5作为文件名
    if name is None:
        name = "%s.mp4" % content_md5
 
    # 上传视频到BOS
    bos_client.put_object(bucket_name, name, bytes_io, content_length, content_md5, 'video/mp4')
 
    # 生成预签名URL
    url = bos_client.generate_pre_signed_url(bucket_name, name, expiration_in_seconds=-1).decode()
 
    return url


def upload_mp3_to_bos(video_path, name=None):
    """
    上传视频到BOS，返回视频的预签名URL。
    
    Args:
        video_path (str): 待上传的视频文件路径。
        name (str): BOS中视频的名称。
    
    Returns:
        str: 视频的预签名URL，可用于下载和展示。
    
    Raises:
        None.
    """
    # 以二进制方式读取视频文件
    with open(video_path, 'rb') as video_file:
        bytes_io = BytesIO(video_file.read())
 
    # 计算MD5和内容长度
    content_md5 = get_md5_from_fp(bytes_io, buf_size=bos_client.config.recv_buf_size)
    content_length = bytes_io.getbuffer().nbytes
 
    # 如果没有指定文件名，使用MD5作为文件名
    if name is None:
        name = "%s.mp4" % content_md5
 
    # 上传视频到BOS
    bos_client.put_object(bucket_name, name, bytes_io, content_length, content_md5, 'audio/wav')
 
    # 生成预签名URL
    url = bos_client.generate_pre_signed_url(bucket_name, name, expiration_in_seconds=-1).decode()
    return url


def upload_file_to_bos(video_path, name=None):
    """
    上传视频到BOS，返回视频的预签名URL。
    
    Args:
        video_path (str): 待上传的视频文件路径。
        name (str): BOS中视频的名称。
    
    Returns:
        str: 视频的预签名URL，可用于下载和展示。
    
    Raises:
        None.
    """
    # 以二进制方式读取视频文件
    with open(video_path, 'rb') as video_file:
        bytes_io = BytesIO(video_file.read())
 
    # 计算MD5和内容长度
    content_md5 = get_md5_from_fp(bytes_io, buf_size=bos_client.config.recv_buf_size)
    content_length = bytes_io.getbuffer().nbytes
 
    # 如果没有指定文件名，使用MD5作为文件名
    if name is None:
        name = "%s.mp4" % content_md5
 
    # 上传视频到BOS
    bos_client.put_object(bucket_name, name, bytes_io, content_length, content_md5, 'file')
 
    # 生成预签名URL
    url = bos_client.generate_pre_signed_url(bucket_name, name, expiration_in_seconds=-1).decode()
    
    return url


if __name__ == '__main__':
    # 上传 /home/data/1029_ad_video2/test 目录下的图像到 BOS
    test_dir = '/home/data/1029_ad_video2/test'
    output_file = '/home/data/1029_ad_video2/utils/upload_results.txt'

    results = {}
    m = 1
    for filename in os.listdir(test_dir):

        file_path = os.path.join(test_dir, filename)
        if os.path.isfile(file_path):
            # 根据文件扩展名选择处理方式
            ext = filename.lower().split('.')[-1]
            if ext in ['jpg', 'jpeg', 'png']:
                # 读取图像并上传
                img = Image.open(file_path)
                url = upload_bos_image(img, filename)
                results[f"image{m}"] = url
                m += 1
                print(m)
                print(f"上传成功: {filename} -> {url}")

    # 保存结果到文件
    with open(output_file, 'w', encoding='utf-8') as f:
    
        f.write(str(results) + '\n')

    print(f"\n共上传 {len(results)} 个文件，结果已保存到: {output_file}")
 