import base64  
import requests  
import json  
import mimetypes  
from pathlib import Path  
from typing import List, Optional, Dict, Any  
import time
import os
  
class QianfanViduAPIClient:  
    """百度千帆 Vidu API 客户端，用于参考图生成视频"""  
    def __init__(self, api_key: str, app_id: str):  
        """  
        初始化百度千帆 Vidu API 客户端  
          
        Args:  
            api_key: 你的千帆 API Key (BCE 格式)
            app_id: 你的应用 ID
        """  
        self.api_key = api_key
        self.app_id = app_id
        self.base_url = "https://qianfan.baidubce.com/beta/video/generations/vidu"
      
    def get_headers(self) -> Dict[str, str]:
        """
        获取请求头
        
        Returns:
            请求头字典
        """
        return {
            "Content-Type": "application/json",
            "appId": self.app_id,
            "Authorization": f"Bearer {self.api_key}"
        }
      
    def image_to_base64(self, image_path: str) -> str:  
        """  
        将图片文件转换为 base64 编码字符串  
          
        Args:  
            image_path: 图片文件路径  
              
        Returns:  
            base64 编码的图片字符串（包含 data URI 前缀）  
        """  
        # 获取文件的 MIME 类型  
        mime_type, _ = mimetypes.guess_type(image_path)  
        if mime_type is None:  
            # 根据文件扩展名手动判断  
            ext = Path(image_path).suffix.lower()  
            mime_map = {  
                '.png': 'image/png',  
                '.jpg': 'image/jpeg',  
                '.jpeg': 'image/jpeg',  
                '.webp': 'image/webp'  
            }  
            mime_type = mime_map.get(ext, 'image/png')  
          
        # 读取图片并转换为 base64  
        with open(image_path, 'rb') as image_file:  
            image_data = image_file.read()  
              
            # 检查文件大小  
            file_size_mb = len(image_data) / (1024 * 1024)  
            if file_size_mb > 10:  
                raise ValueError(f"图片文件过大: {file_size_mb:.2f}MB，base64 解码后需小于 10MB")  
              
            encoded_string = base64.b64encode(image_data).decode('utf-8')  
          
        # 返回完整的 data URI  
        return f"data:{mime_type};base64,{encoded_string}"  
      
    def text2video(self, 
                     prompt: str,
                     model: str = "viduq2",
                     duration: int = 5,
                     seed: int = 0,
                     resolution: str = "720p",
                     aspect_ratio: str = "16:9") -> Dict[str, Any]:
       
        # 验证模型
        valid_models = ["ernie_video_1.0", "viduq1", "vidu2.0", "vidu1.5", "viduq2"]
        if model not in valid_models:
            raise ValueError(f"无效的模型: {model}，可选值: {', '.join(valid_models)}")
            
        # 验证提示词长度
        if len(prompt) > 2000:
            raise ValueError(f"提示词过长: {len(prompt)} 字符，最多支持 2000 字符")
            
        # 构建请求体
        request_body = {
            "model": model,
            "prompt": prompt,
            "seed": seed,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution
        }
        
        # 发送请求
        url = f"{self.base_url}/v2/text2video"
        headers = self.get_headers()
        print(f"\n正在发送请求到: {url}")
        print(f"请求头: appId={self.app_id}")
        print(f"请求参数: model={model}, prompt长度={len(prompt)}")
        
        try:
            response = requests.post(url, headers=headers, json=request_body, timeout=60)
            
            # 处理响应
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f"\n=== API 响应 ===")
                    print(f"视频生成成功，视频URL: {result.get('video_url', '未获取到视频URL')}")
                    print(f"======================\n")
                    return result
                except json.JSONDecodeError:
                    print(f"\n无法解析 API 响应为 JSON。原始响应: {response.text}")
                    raise Exception("API 响应格式错误")
            else:
                print(f"\nAPI 请求失败，状态码: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
                except:
                    print(f"响应内容: {response.text}")
                raise Exception(f"API 请求失败，状态码: {response.status_code}")
                
        except requests.exceptions.Timeout:
            raise Exception("请求超时（60秒），请检查网络连接或稍后重试")
        except requests.exceptions.ConnectionError:
            raise Exception("无法连接到千帆 API 服务器，请检查网络")
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求异常: {str(e)}")

    def reference2video(  
        self,  
        images: List[str],  
        prompt: str,  
        model: str = "viduq2",  # 默认 viduq1
        duration: Optional[int] = None,  
        seed: int = 0,  
        aspect_ratio: str = "16:9",  
        resolution: Optional[str] = None,  
        movement_amplitude: str = "auto"  
    ) -> Dict[str, Any]:  
        """  
        参考生视频接口（百度千帆版本）  
          
        Args:  
            images: 图片列表，可以是本地路径或 URL  
                   - 本地路径会自动转换为 base64  
                   - URL 直接使用  
                   - viduq1: 支持 1-7 张图片  
                   - vidu2.0/vidu1.5: 支持 1-3 张图片  
            prompt: 文本提示词（最多 1500 字符）  
            model: 模型名称，可选值：  
                   - viduq1：画面清晰，平滑转场，运镜稳定（推荐）
                   - vidu2.0：生成速度快  
                   - vidu1.5：动态幅度大  
            duration: 视频时长（秒）  
                     - viduq1: 5秒（默认）  
                     - vidu2.0: 4秒（默认）  
                     - vidu1.5: 4或8秒（默认4秒）  
            seed: 随机种子，0 表示随机  
            aspect_ratio: 比例，可选：16:9、9:16、1:1  
            resolution: 分辨率  
                       - viduq1 (5秒): 默认 1080p, 可选：1080p  
                       - vidu2.0 (4秒): 默认 360p, 可选：360p、720p  
                       - vidu1.5 (4秒): 默认 360p，可选：360p、720p、1080p  
                       - vidu1.5 (8秒): 默认 720p，可选：720p  
            movement_amplitude: 运动幅度，可选：auto、small、medium、large  
              
        Returns:  
            API 响应结果  
        """  
        # 验证模型
        valid_models = ["viduq1", "vidu2.0", "vidu1.5", "viduq2"]
        if model not in valid_models:
            raise ValueError(f"无效的模型: {model}，可选值: {', '.join(valid_models)}")
        
        # 验证提示词长度  
        if len(prompt) > 1500:  
            raise ValueError(f"提示词过长: {len(prompt)} 字符，最多支持 1500 字符")  
          
        # 验证图片数量  
        if model == "viduq1":  
            if len(images) < 1 or len(images) > 7:  
                raise ValueError(f"viduq1 模型支持 1-7 张图片，当前: {len(images)} 张")  
        elif model in ["vidu2.0", "vidu1.5"]:  
            if len(images) < 1 or len(images) > 3:  
                raise ValueError(f"{model} 模型支持 1-3 张图片，当前: {len(images)} 张")  
          
        # 处理图片：本地路径转 base64，URL 直接使用  
        processed_images = []  
        for i, img in enumerate(images):  
            if img.startswith('http://') or img.startswith('https://'):  
                # URL 直接使用  
                print(f"使用图片 URL [{i+1}/{len(images)}]: {img[:80]}...")  
                processed_images.append(img)  
            else:  
                # 本地文件转 base64  
                print(f"正在转换图片 [{i+1}/{len(images)}]: {img}")  
                processed_images.append(self.image_to_base64(img))  
          
        # 构建请求体  
        request_body = {  
            "model": model,  
            "images": processed_images,  
            "prompt": prompt,  
            "seed": seed,  
            "aspect_ratio": aspect_ratio,  
            "movement_amplitude": movement_amplitude

        }  
          
        # 添加可选参数  
        if duration is not None:  
            request_body["duration"] = duration  
        if resolution is not None:  
            request_body["resolution"] = resolution  
          
        # 发送请求
        url = f"{self.base_url}/v2/reference2video"
        headers = self.get_headers()
          
        print(f"\n正在发送请求到: {url}")  
        print(f"请求头: appId={self.app_id}")
        print(f"请求参数: model={model}, 图片数={len(images)}, prompt长度={len(prompt)}")  
          
        try:  
            response = requests.post(url, headers=headers, json=request_body, timeout=60)  
              
            # 打印调试信息  
            print(f"\n=== API 响应调试信息 ===")  
            print(f"HTTP 状态码: {response.status_code}")  
              
            # 检查 HTTP 状态码  
            if response.status_code != 200:  
                print(f"响应内容: {response.text}")  
                error_msg = f"API 请求失败，状态码: {response.status_code}"  
                try:  
                    error_data = response.json()  
                    error_msg += f"\n错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}"  
                except:  
                    error_msg += f"\n响应内容: {response.text}"  
                print(f"======================\n")
                raise Exception(error_msg)  
              
            # 尝试解析 JSON  
            try:  
                result = response.json()  
                # print(f"响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")  
                print(f"======================\n")  
                return result  
            except json.JSONDecodeError as e:  
                print(f"响应内容: {response.text}")  
                print(f"======================\n")  
                raise Exception(f"无法解析 API 响应为 JSON。原始响应: {response.text}")  
                  
        except requests.exceptions.Timeout:  
            raise Exception("请求超时（60秒），请检查网络连接或稍后重试")  
        except requests.exceptions.ConnectionError:  
            raise Exception("无法连接到千帆 API 服务器，请检查网络")  
        except requests.exceptions.RequestException as e:  
            raise Exception(f"请求异常: {str(e)}")  


    def startend2video(
        self,  
        images: List[str],  
        prompt: str,  
        model: str = "viduq2-pro",  # 默认 viduq1
        duration: Optional[int] = None,  
        seed: int = 0,  
        aspect_ratio: str = "16:9",  
        resolution: Optional[str] = None,  
        movement_amplitude: str = "auto"  
    ) -> Dict[str, Any]:
        """
        首尾帧生视频接口（百度千帆版本）
        
        Args:
            images: 图片列表，必须是2张图片（首帧和尾帧）
                - 本地路径会自动转换为 base64
                - URL 直接使用
            prompt: 文本提示词，描述从首帧到尾帧的变化过程
            model: 模型名称，默认使用 viduq1-classic
            seed: 随机种子，0 表示随机
            **kwargs: 其他可能的API参数
            
        Returns:
            API 响应结果
        """
        # 验证图片数量 - 首尾帧需要正好2张图片
        if len(images) != 2:
            raise ValueError(f"首尾帧生成需要2张图片（首帧和尾帧），当前: {len(images)} 张")
        
        # 验证提示词长度
        if len(prompt) > 1500:
            raise ValueError(f"提示词过长: {len(prompt)} 字符，最多支持 1500 字符")
        
        # 处理图片：本地路径转 base64，URL 直接使用
        processed_images = []
        for i, img in enumerate(images):
            if img.startswith('http://') or img.startswith('https://'):
                # URL 直接使用
                print(f"使用图片 URL [{i+1}/{len(images)}]: {img[:80]}...")
                processed_images.append(img)
            else:
                # 本地文件转 base64
                print(f"正在转换图片 [{i+1}/{len(images)}]: {img}")
                processed_images.append(self.image_to_base64(img))
        
        # 构建请求体
        request_body = {
            "model": model,
            "images": processed_images,
            "prompt": prompt,
            "seed": seed,
            "aspect_ratio": aspect_ratio,  
            "duration":duration,
            "movement_amplitude": movement_amplitude
        }
        
        # 添加其他可选参数
        
        # 发送请求到首尾帧专用接口
        url = f"{self.base_url}/v2/startend2video"
        headers = self.get_headers()
        
        print(f"\n正在发送请求到: {url}")
        print(f"请求头: appId={self.app_id}")
        print(f"请求参数: model={model}, 首尾帧图片数={len(images)}, prompt长度={len(prompt)}")
        
        try:
            response = requests.post(url, headers=headers, json=request_body, timeout=60)
            
            # 打印调试信息
            print(f"\n=== API 响应调试信息 ===")
            print(f"HTTP 状态码: {response.status_code}")
            
            # 检查 HTTP 状态码
            if response.status_code != 200:
                print(f"响应内容: {response.text}")
                error_msg = f"API 请求失败，状态码: {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg += f"\n错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}"
                except:
                    error_msg += f"\n响应内容: {response.text}"
                print(f"======================\n")
                raise Exception(error_msg)
            
            # 尝试解析 JSON
            try:
                result = response.json()
                print(f"======================\n")
                return result
            except json.JSONDecodeError as e:
                print(f"响应内容: {response.text}")
                print(f"======================\n")
                raise Exception(f"无法解析 API 响应为 JSON。原始响应: {response.text}")
                
        except requests.exceptions.Timeout:
            raise Exception("请求超时（60秒），请检查网络连接或稍后重试")
        except requests.exceptions.ConnectionError:
            raise Exception("无法连接到千帆 API 服务器，请检查网络")
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求异常: {str(e)}")
        

    def image2video(  
        self,  
        images: List[str],  
        prompt: str,  
        model: str = "viduq2-turbo",  # 默认 viduq1
        duration: Optional[int] = None,  
        seed: int = 0,  
        aspect_ratio: str = "16:9",  
        resolution: Optional[str] = None,  
        movement_amplitude: str = "auto"  
    ) -> Dict[str, Any]:    
        
        # 验证提示词长度  
        if len(prompt) > 1500:  
            raise ValueError(f"提示词过长: {len(prompt)} 字符，最多支持 1500 字符") 
          
        # 处理图片：本地路径转 base64，URL 直接使用  
        processed_images = []  
        for i, img in enumerate(images):  
            if img.startswith('http://') or img.startswith('https://'):  
                # URL 直接使用  
                print(f"使用图片 URL [{i+1}/{len(images)}]: {img[:80]}...")  
                processed_images.append(img)  
            else:  
                # 本地文件转 base64  
                print(f"正在转换图片 [{i+1}/{len(images)}]: {img}")  
                processed_images.append(self.image_to_base64(img))  
          
        # 构建请求体  
        request_body = {  
            "model": model,  
            "images": processed_images,  
            "prompt": prompt,  
            "seed": seed,  
            "aspect_ratio": aspect_ratio,  
            "movement_amplitude": movement_amplitude  
        }  
          
        # 添加可选参数  
        if duration is not None:  
            request_body["duration"] = duration  
        if resolution is not None:  
            request_body["resolution"] = resolution  
          
        # 发送请求
        url = f"{self.base_url}/v2/image2video"
        headers = self.get_headers()
          
        print(f"\n正在发送请求到: {url}")  
        print(f"请求头: appId={self.app_id}")
        print(f"请求参数: model={model}, 图片数={len(images)}, prompt长度={len(prompt)}")  
          
        try:  
            response = requests.post(url, headers=headers, json=request_body, timeout=60)  
              
            # 打印调试信息  
            print(f"\n=== API 响应调试信息 ===")  
            print(f"HTTP 状态码: {response.status_code}")  
              
            # 检查 HTTP 状态码  
            if response.status_code != 200:  
                print(f"响应内容: {response.text}")  
                error_msg = f"API 请求失败，状态码: {response.status_code}"  
                try:  
                    error_data = response.json()  
                    error_msg += f"\n错误详情: {json.dumps(error_data, indent=2, ensure_ascii=False)}"  
                except:  
                    error_msg += f"\n响应内容: {response.text}"  
                print(f"======================\n")
                raise Exception(error_msg)  
              
            # 尝试解析 JSON  
            try:  
                result = response.json()  
                # print(f"响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")  
                print(f"======================\n")  
                return result  
            except json.JSONDecodeError as e:  
                print(f"响应内容: {response.text}")  
                print(f"======================\n")  
                raise Exception(f"无法解析 API 响应为 JSON。原始响应: {response.text}")  
                  
        except requests.exceptions.Timeout:  
            raise Exception("请求超时（60秒），请检查网络连接或稍后重试")  
        except requests.exceptions.ConnectionError:  
            raise Exception("无法连接到千帆 API 服务器，请检查网络")  
        except requests.exceptions.RequestException as e:  
            raise Exception(f"请求异常: {str(e)}")  
      
    def query_task(self, task_id: str) -> Dict[str, Any]:  
        """  
        查询任务状态  
          
        Args:  
            task_id: 任务 ID  
              
        Returns:  
            任务状态信息  
        """  
        headers = self.get_headers()
          
        print(f"\n正在查询任务: {task_id}")  
        if not task_id:
            raise Exception("创建失败，未返回 task_id")

        query_url = "https://qianfan.baidubce.com/beta/video/generations/vidu/v2/creations"

        print(f"查询任务状态: {task_id}")
        video_url = None

        query_params = {"task_id": task_id}
        query_resp = requests.get(query_url, headers=headers, params=query_params)
        data = query_resp.json()
        return data

def download_video(url, save_path):
    for i in range(10):
        print(f"下载视频第{i + 1}次...")
        try:
            response = requests.get(url, stream=True, verify=False)

            if response.status_code == 200:
                # 打开文件以二进制写入方式保存视频
                with open(save_path, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                print("视频下载完成")
                return True
            else:
                print("请求失败，状态码：", response.status_code)
                raise Exception("请求失败")
        except Exception as e:
            print("下载视频请求异常：", e)
            time.sleep(i + 5)


def gen_video_by_qianfan(prompt, image_urls, aspect_ratio="9:16", duration=4, resolution="720p", model="viduq2",
                        save_video_path="./video_by_vidu.mp4"):
    APP_ID = "app-bHIRne58"
    API_KEY = "bce-v3/ALTAK-urM8m2wa2JGBqTKDaEelR/a0978e91872deb2da0331a781eca30275f54ffea"

    # 初始化千帆客户端
    
    client = QianfanViduAPIClient(api_key=API_KEY, app_id=APP_ID)

    try:
        result = client.reference2video(
            images=image_urls,
            prompt=prompt,
            model=model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            movement_amplitude="medium",
        )
    except Exception as e:
        raise Exception(f"创建任务失败: {e}, promt: {prompt}")
    
    print(f"\n任务已创建成功, promt: {prompt}")
    task_id = result.get("task_id")
    print(f"task_id:{task_id}")

    # 轮询查询任务，判断是否结束
    start_time = time.time()
    timeout = 1000
    while time.time() - start_time < timeout:
        response_data = client.query_task(task_id)

        if response_data is None:
            print("Error: No response from API")
            break

        status = response_data.get("status")
        print(f"Status:{status}, response_data:{response_data}")

        if status != "success":
            print("Still waiting... Checking again in 20 seconds.")
            time.sleep(20)
        else:
            url = response_data["creations"][0]["url"]
            print(f"视频生成成功, url:{url}")
            download_video(url, save_video_path)

            # 计算总耗时并转换为分钟格式
            total_seconds = time.time() - start_time
            total_minutes = total_seconds / 60
            print(f"总共耗时: {total_minutes:.2f}分钟, 视频保存至: {save_video_path}")
            return "1"

    # 如果超时退出循环
    total_seconds = time.time() - start_time
    total_minutes = total_seconds / 60
    print(f"任务超时，总耗时: {total_minutes:.2f}分钟")
    return task_id

def gen_video_by_qianfan_withstartend(prompt, image_urls, aspect_ratio=None, duration=4, resolution="720p", model="viduq2-turbo",
                        save_video_path="./video_by_vidu.mp4"):
    APP_ID = "app-bHIRne58"
    API_KEY = "bce-v3/ALTAK-urM8m2wa2JGBqTKDaEelR/a0978e91872deb2da0331a781eca30275f54ffea"

    # 初始化千帆客户端
    # 可选模型：viduq2-pro、viduq2-turbo、viduq1、viduq1-classic、vidu2.0
    client = QianfanViduAPIClient(api_key=API_KEY, app_id=APP_ID)

    try:
        result = client.startend2video(
            images=image_urls,
            prompt=prompt,
            model=model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            movement_amplitude="medium"
        )
    except Exception as e:
        raise Exception(f"创建任务失败: {e}, promt: {prompt}")
    
    print(f"\n任务已创建成功, promt: {prompt}")
    task_id = result.get("task_id")
    print(f"task_id:{task_id}")

    # 轮询查询任务，判断是否结束
    start_time = time.time()
    timeout = 1000
    while time.time() - start_time < timeout:
        response_data = client.query_task(task_id)

        if response_data is None:
            print("Error: No response from API")
            break

        status = response_data.get("status")
        print(f"Status:{status}, response_data:{response_data}")

        if status != "success":
            print("Still waiting... Checking again in 20 seconds.")
            time.sleep(20)
        else:
            url = response_data["creations"][0]["url"]
            print(f"视频生成成功, url:{url}")
            download_video(url, save_video_path)

            # 计算总耗时并转换为分钟格式
            total_seconds = time.time() - start_time
            total_minutes = total_seconds / 60
            print(f"总共耗时: {total_minutes:.2f}分钟, 视频保存至: {save_video_path}")
            return "1"

    # 如果超时退出循环
    total_seconds = time.time() - start_time
    total_minutes = total_seconds / 60
    print(f"任务超时，总耗时: {total_minutes:.2f}分钟")
    return task_id


def gen_video_by_qianfan_with_image2video(prompt, image_urls, aspect_ratio="9:16", duration=4, resolution="720p", model="viduq2",
                        save_video_path="./video_by_vidu.mp4"):
    APP_ID = "app-bHIRne58"
    API_KEY = "bce-v3/ALTAK-urM8m2wa2JGBqTKDaEelR/a0978e91872deb2da0331a781eca30275f54ffea"

    # 初始化千帆客户端
    client = QianfanViduAPIClient(api_key=API_KEY, app_id=APP_ID)

    try:
        result = client.image2video(
            images=image_urls,
            prompt=prompt,
            model=model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            movement_amplitude="medium",
        )
    except Exception as e:
        raise Exception(f"创建任务失败: {e}, promt: {prompt}")
    
    print(f"\n任务已创建成功, promt: {prompt}")
    task_id = result.get("task_id")
    print(f"task_id:{task_id}")

    # 轮询查询任务，判断是否结束
    start_time = time.time()
    timeout = 1000
    while time.time() - start_time < timeout:
        response_data = client.query_task(task_id)

        if response_data is None:
            print("Error: No response from API")
            break

        status = response_data.get("status")
        print(f"Status:{status}, response_data:{response_data}")

        if status != "success":
            print("Still waiting... Checking again in 20 seconds.")
            time.sleep(20)
        else:
            url = response_data["creations"][0]["url"]
            print(f"视频生成成功, url:{url}")
            download_video(url, save_video_path)

            # 计算总耗时并转换为分钟格式
            total_seconds = time.time() - start_time
            total_minutes = total_seconds / 60
            print(f"总共耗时: {total_minutes:.2f}分钟, 视频保存至: {save_video_path}")
            return

    # 如果超时退出循环
    total_seconds = time.time() - start_time
    total_minutes = total_seconds / 60
    print(f"任务超时，总耗时: {total_minutes:.2f}分钟")


# 文生视频
def gen_video_by_qianfan_with_text2video(prompt, aspect_ratio="9:16", duration=4, resolution="720p", model="viduq2",
                        save_video_path="./video_by_vidu.mp4"):
    """
    使用千帆API通过文本生成视频

    该函数调用千帆的文本转视频API，根据提供的提示词生成视频文件，并支持等待任务完成和下载结果。

    Args:
        prompt: 文本提示词，描述要生成的视频内容
        aspect_ratio: 视频宽高比，默认为"9:16"
        duration: 视频时长（秒），默认为4秒
        resolution: 视频分辨率，默认为"720p"
        model: 使用的模型名称，默认为"viduq2"
        save_video_path: 视频保存路径，默认为"./video_by_vidu.mp4"

    Returns:
        None

    Raises:
        Exception: 当任务创建失败或API调用异常时抛出
    """
    APP_ID = "app-bHIRne58"
    API_KEY = "bce-v3/ALTAK-urM8m2wa2JGBqTKDaEelR/a0978e91872deb2da0331a781eca30275f54ffea"

    # 初始化千帆客户端
    client = QianfanViduAPIClient(api_key=API_KEY, app_id=APP_ID)

    try:
        print("开始使用vidu 文生视频")
        result = client.text2video(
            prompt=prompt,
            model=model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
        )
    except Exception as e:
        raise Exception(f"创建任务失败: {e}, promt: {prompt}")
    
    print(f"\n任务已创建成功, promt: {prompt}")
    task_id = result.get("task_id")
    print(f"task_id:{task_id}")

    # 轮询查询任务，判断是否结束
    start_time = time.time()
    timeout = 1000
    while time.time() - start_time < timeout:
        response_data = client.query_task(task_id)

        if response_data is None:
            print("Error: No response from API")
            break

        status = response_data.get("status")
        print(f"Status:{status}, response_data:{response_data}")

        if status != "success":
            print("Still waiting... Checking again in 20 seconds.")
            time.sleep(20)
        else:
            url = response_data["creations"][0]["url"]
            print(f"视频生成成功, url:{url}")
            download_video(url, save_video_path)

            # 计算总耗时并转换为分钟格式
            total_seconds = time.time() - start_time
            total_minutes = total_seconds / 60
            print(f"总共耗时: {total_minutes:.2f}分钟, 视频保存至: {save_video_path}")
            return

    # 如果超时退出循环
    total_seconds = time.time() - start_time
    total_minutes = total_seconds / 60
    print(f"任务超时，总耗时: {total_minutes:.2f}分钟")



if __name__ == "__main__":  
    image_urls = [
        "/home/data/1029_ad_video2/short_play/草船借箭/images/1.jpg"
    ]
    
    prompts = f"诸葛亮走到帐篷中间，对着众人讲话。"
    save_path = "/home/data/1029_ad_video2/short_play/草船借箭/images/test.mp4"
    gen_video_by_qianfan_with_image2video(prompts,image_urls,aspect_ratio="16:9", duration=5,  model="viduq2-turbo",save_video_path=save_path)
    

    #gen_video_by_qianfan(prompts, image_urls,  duration=4 ,save_video_path=save_path)

    # 初始化千帆客户端
    # client = QianfanViduAPIClient(api_key=API_KEY, app_id=APP_ID)
    # start_time = time.time()
    # timeout = 1000
    # while time.time() - start_time < timeout:
    #     response_data = client.query_task(task_id)

    #     if response_data is None:
    #         print("Error: No response from API")
    #         break

    #     status = response_data.get("status")
    #     print(f"Status:{status}, response_data:{response_data}")

    #     if status != "success":
    #         print("Still waiting... Checking again in 20 seconds.")
    #         time.sleep(20)
    #     else:
    #         url = response_data["creations"][0]["url"]
    #         print(f"视频生成成功, url:{url}")
    #         download_video(url, save_video_path)

    #         # 计算总耗时并转换为分钟格式
    #         total_seconds = time.time() - start_time
    #         total_minutes = total_seconds / 60
    #         print(f"总共耗时: {total_minutes:.2f}分钟, 视频保存至: {save_video_path}")
    #         break

