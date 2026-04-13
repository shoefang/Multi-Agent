"""四宫格生成方案"""

from utils.nano_banana import NanobananaAspectRatio
from utils.nano_banana_vod import GeminiVodImageGenerator
from utils.convert2prompt_4 import generate_prompts, extract_aspect_ratio
from utils.postprocess_2x2 import split_image_list, detect_case_valid
from utils.compress import compress_image_quality
from utils.download import robust_download
#import utils.critical as critical

import json
import os
from PIL import Image
import base64
from pathlib import Path
import io
import time




class Image2x2Generator:
    """
    四宫格生成图片的方案
    """
    def __init__(self) -> None:
        #self.nano_banana = NanobananaImageGenerator() # 原始的gemini
        self.nano_banana = GeminiVodImageGenerator() # vod格式
        # self.nano_banana_aspect_ratio = NanobananaAspectRatio

    def result_to_pil_image(self, result: dict) -> Image.Image:
        '''
        result: dict, 将其中的image_data字段解码然后转化为PIL
        '''
        if "image_data" not in result:
           return None

        img_data = result["image_data"]
        print("result image type:", type(img_data))

        # 如果是字符串 → 说明是 base64
        if isinstance(img_data, str):
            img_bytes = base64.b64decode(img_data)
        else:
            # 如果是 bytes → 直接用
            img_bytes = img_data

        # # base64 -> bytes
        # img_bytes = base64.b64decode(result["image_data"])

        # bytes -> PIL Image
        img = Image.open(io.BytesIO(img_bytes))

        # 可选：有些模型返回的是 lazy image，最好 load 一下
        img.load()

        return img
    
    def encode_image_to_base64(self, image_path):
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
        

    def generate(self, outline, reference_imgs=[], save_dir=""):
        """
        生成-主函数
        """
        # step1: 加载已有文件
        results_file = os.path.join(save_dir, "results.json")
        if os.path.exists(results_file):
            with open(results_file, "r") as f:
                results_dict = json.load(f)
        else:
            results_dict = {}
        # step2
        aspect_ratio = extract_aspect_ratio(outline)
        prompt_file = os.path.join(save_dir, "prompt.json")
        print("prompt_file:", prompt_file)
        # if not os.path.exists(prompt_file):
        prompts, total_num = generate_prompts(outline)
        print("prompts:", prompts, "total_num:", total_num, "aspect_ratio:", aspect_ratio, "reference_imgs:", reference_imgs)
        with open(prompt_file, "w") as f:
            f.write(json.dumps({"prompts": prompts, "total_num": total_num}, ensure_ascii=False, indent=True))
        # else:
        #     with open(prompt_file, "r") as f:
        #         temp_data = json.load(f)
        #     print("temp_data:", temp_data)
        #     prompts = temp_data["prompts"]
        #     total_num = temp_data["total_num"]
        aspect_map = {"1:1": NanobananaAspectRatio.SQUARE,
                  "16:9": NanobananaAspectRatio.LANDSCAPE,
                  "9:16": NanobananaAspectRatio.PORTRAIT,
                  "4:3": NanobananaAspectRatio.WIDE,
                  "3:4": NanobananaAspectRatio.TALL}
        reference_img = []
        if aspect_ratio == "1:1":
            reference_img = ["http://miaobi-general-product.bj.bcebos.com/b%27v0MDKMvHZox36wuZ01jj4w%3D%3D%27.png?authorization=bce-auth-v1%2FALTAKmda7zOvhZVbRzBLewvCMU%2F2026-03-04T09%3A22%3A23Z%2F-1%2F%2F9969789467b23ca473afff0a373e654045442fae9523996d0251a555d07bb781"]
            # reference_img = [self.encode_image_to_base64("template/grid_1_1.png")]
        elif aspect_ratio == "3:4":
            reference_img = ["http://miaobi-general-product.bj.bcebos.com/b%27oVyf9B%2BBwh%2B0Esed/AqD7w%3D%3D%27.png?authorization=bce-auth-v1%2FALTAKmda7zOvhZVbRzBLewvCMU%2F2026-03-04T09%3A23%3A23Z%2F-1%2F%2Fef946bada7d177cda4acffb7b83a37eaccc05d4c953b99c0c428328120ffb164"]
            # reference_img = [self.encode_image_to_base64("template/grid_3_4.png")]
        
        # 所有的单图结果
        results = []
        # 新增重试机制
        for idx, prompt in enumerate(prompts, start=1):
            if save_dir:
                result_path = os.path.join(save_dir, f"{idx}.png")
            else:
                result_path = ""

            max_tries = 3 # 正常尝试 1 次 + 重试 3 次
            generation_success = False
            img = None
            success = False

            # 2. 引入重试机制
            for attempt in range(max_tries):
                is_valid = False
                img = None
                if attempt == 0:
                    if result_path and os.path.exists(result_path):
                        print(f"尝试读取本地缓存文件: {result_path}")
                        img = Image.open(result_path)
                    
                    elif str(idx) in results_dict:
                        print(f"尝试从结果字典中的 URL 下载...")
                        image_url = results_dict[str(idx)]["image_url"]
                        download_result = robust_download(image_url)
                        if download_result.get("status") == "SUCCESS":
                            result = {"image_data": download_result["image_data"], "image_url": image_url}
                            img = Image.open(io.BytesIO(result["image_data"]))

                    # 如果第一次尝试且缓存(文件或URL)有效，直接成功并跳出
                    else:
                        print(f"第 {idx} 个结果需调用模型生成 (当前生成尝试: {attempt + 1}/{max_tries})...")

                if not img:
                    result = self.nano_banana.generate(prompt, image=reference_img, aspect_ratio=aspect_map[aspect_ratio])
                    if result["status"] != "SUCCESS":
                        continue
            
                    # 重新生成后，覆盖字典中的旧 URL
                    results_dict[str(idx)] = {
                        "image_url": result.get("image_url", ""),
                        "prompt": prompt
                    }
                    # 实时写入文件
                    with open(results_file, "w") as f:
                        json.dump(results_dict, f, indent=2, ensure_ascii=False)

                    # 处理生成的图片数据并校验
                    if "image_data" in result:
                        img = self.result_to_pil_image(result)
                    if result_path:
                        compress_image_quality(img, save_dir=result_path)
                
                print("检查四宫格是否合规...")
                is_valid = detect_case_valid(result_path)
                if not is_valid:
                    print(f"校验失败：生成的图片不是四宫格，准备进行下一次重试...")
                    continue
                
                # 审核校验
                print("进行多模态机审...")
                split_results = split_image_list(img)
                split_results = split_results[: min(total_num, 4)]
                #review_ans = critical.review_image(split_results, prompt, save_dir)
                review_ans = split_results
                # 不要管True，因为上面有可能是False
                if not review_ans:
                    print("校验失败：审核失败，准备进行下一次重试")
                    continue

                if is_valid:
                    success = True
                    print(f"第 {idx} 个结果生成且校验通过！")
                    break
                else:
                    continue
                    

            if not success:
                raise Exception(f"生成失败: 第 {idx} 个 prompt 在尝试 {max_tries} 次后，依然未能获取/生成合规的四宫格图片。")
            
            if len(split_results):
                results += split_results
                total_num -= len(split_results)
            print(f"第 {idx} 个结果处理完成。")

        return results





if __name__ == "__main__":
    generator = Image2x2Generator()
    result_dir = '/home/work/data/lhn/0302/code_信息图/results/result_0301/米色最忌三种颜色'
    md_file = "/home/work/data/lhn/0302/code_信息图/results/result_0301/米色最忌三种颜色/outline.md"
    with open(md_file, "r", encoding="utf-8") as f:
        outline_md = f.read()
    results = generator.generate(outline_md, save_dir=result_dir)
    for i, result in enumerate(results, start=1):
        compress_image_quality(result, quality=90, save_dir=f"{result_dir}/{i}.png")
    end_time = time.time()


