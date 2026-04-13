import os
import requests
from typing import Optional, Union
import glob
import pandas as pd
from pathlib import Path
from utils.downloads import download_file

class DigitalHumanClient:
    def __init__(self, server_url="http://10.223.9.144:8534"):
        self.server_url = server_url
        self.process_endpoint = f"{server_url}/process"
    
    def process_media(
        self,
        video_input: Union[str, bytes],  # 可以是文件路径或URL
        audio_path: str,
        video_is_url: bool = False
    ) -> Optional[str]:
        """
        处理媒体文件并返回视频URL
        :param video_input: 输入视频(文件路径或URL字符串)
        :param audio_path: 输入音频路径
        :param video_is_url: 是否使用视频URL模式
        :return: 处理后的视频URL，失败返回None
        """
        try:
            # 验证音频文件是否存在
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
            # 准备请求数据
            files = {
                'audio': open(audio_path, 'rb')
            }
            
            data = {}
            
            if video_is_url:
                # URL模式
                if not isinstance(video_input, str):
                    raise ValueError("video_input must be URL string when video_is_url=True")
                data['video_url'] = video_input
            else:
                # 文件模式
                if not os.path.exists(video_input):
                    raise FileNotFoundError(f"Video file not found: {video_input}")
                files['video'] = open(video_input, 'rb')
            
            # 发送请求
            response = requests.post(
                self.process_endpoint,
                files=files,
                data=data,
                timeout=500000  # 根据处理时间调整
            )
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            
            if result.get('status') == 'success':
                video_url = result.get('video_url')
                print(f"处理完成，视频URL: {video_url}")
                return video_url
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"处理失败: {error_msg}")
                return None
            
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {str(e)}")
        except Exception as e:
            print(f"发生错误: {str(e)}")
        finally:
            # 确保文件句柄关闭
            if 'files' in locals():
                for f in files.values():
                    if hasattr(f, 'close'):
                        f.close()
        return None



def gen_video_with_lip_driven(origin_video_path, audio_path, save_video_path):
    client = DigitalHumanClient()
    try:
        result = client.process_media(
            video_input=origin_video_path,
            audio_path=audio_path,
            video_is_url=False
        )
        if not result:
            raise Exception("调用唇形驱动接口返回为空！")
        video_url = str(result)
        download_file(video_url, save_video_path)

    except Exception as e:
        print(f"视频唇形驱动失败:{e}")




if __name__ == '__main__':
    # 初始化客户端
    client = DigitalHumanClient()
    # /home/data/1029_ad_video2/output_multimages/奔驰SL/temp/audio_0.mp3
    video_path = "/home/work/zhuzhonglong/baidu/miaobi/ads_video/asset/test/分镜6_变速后.mp4"
    audio_path="/home/work/zhuzhonglong/baidu/miaobi/ads_video/asset/test/audio_5.mp3"
    result = client.process_media(
        video_input=video_path,
        audio_path=audio_path,
        video_is_url=False
    )
    print(f"video_url：{str(result)}")