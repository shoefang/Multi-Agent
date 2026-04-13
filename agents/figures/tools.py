import json
import sys
import os
import json
import re
from pathlib import Path
import inspect
from datetime import datetime

import ast
from io import BytesIO
import requests
from PIL import Image
from utils.image_api import search_image 
from utils.miaotu_miaoying import generate_image_with_miaotu
from utils.nano_banana_vod import GeminiVodImageGenerator

def read_file(file_path: str) -> str:
    """读取文件内容"""
    path = Path(file_path)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"错误：文件不存在 {file_path}"


def write_file(file_path: str, content: str) -> str:
    """写入文件"""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"已保存到 {file_path}"


def list_directory(dir_path: str) -> str:
    """列出目录内容"""
    path = Path(dir_path)
    if path.exists() and path.is_dir():
        items = [f.name for f in path.iterdir()]
        return json.dumps(items, ensure_ascii=False)
    return f"错误：目录不存在 {dir_path}"


def discover_skills(skills_dir: str) -> str:
    """发现可用的 Skills"""
    path = Path(skills_dir)
    skills = []
    if path.exists():
        for skill_dir in path.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    # 读取 skill 的描述
                    content = skill_md.read_text(encoding="utf-8")
                    # 提取 description
                    match = re.search(r'description:\s*(.+)', content)
                    desc = match.group(1).strip() if match else "No description"
                    skills.append({
                        "name": skill_dir.name,
                        "path": str(skill_md),
                        "description": desc
                    })
    return json.dumps(skills, ensure_ascii=False, indent=2)


def load_skill(skill_path: str) -> str:
    """加载 Skill 的完整指令"""
    return read_file(skill_path)


# 特殊标记：用于 complete_task 工具的返回值
TASK_COMPLETE_SIGNAL = "__TASK_COMPLETE__"

def complete_task(summary: str, files_created: list = None) -> str:
    """
    标记任务完成并退出 Agent 循环。
    这是唯一正确的退出方式。
    """
    result = {
        "status": "completed",
        "summary": summary,
        "files_created": files_created or []
    }
    # 返回特殊标记 + JSON 结果
    return TASK_COMPLETE_SIGNAL + json.dumps(result, ensure_ascii=False)

def download_image(image_url):
        """
        Downloads an image from a URL and returns PIL Image object.
        Returns PIL Image or None if failed.
        """
        to_replace = image_url.split("/")[2]
        image_url = image_url.replace(to_replace, "yawen-gips.baidu-int.com")
        res = requests.get(image_url, timeout=30)
        res.raise_for_status()
        # 直接返回PIL Image对象，不保存到文件
        image = Image.open(BytesIO(res.content)).convert("RGB")
        return image
  
        

 # 搜图
def search(keyword, para, added="[]"):
    """
    搜索图片，需要搜索的图片数量为num_images
    """
    num_images = 5
    images = search_image(keyword, num_images)
    print(images)
    added = ast.literal_eval(added)
    url_list = [x['url'] for x in added]
    for image in images:
        url = image["url"]
        if url in url_list:
            continue
        image_data = download_image(url)
        if image_data is None:
            continue
        w, h = image_data.size[:2]
        if h / w > 1:
            continue
        if min(h, w) < 400: 
            continue
        else:
            data = {'url': url, 'desc': image['desc'], "段落": para}
            print(data)
            added.append(data)
            return str(added)
    return str(added)


#生成配图
# def generate_image(prompt):
#     """
#     生成图片
#     """
#     image_url = generate_image_with_miaotu(prompt)
#     return image_url

def generate_image(
    prompt: str,
    save_path: str,
    image_urls: list = None,
    aspect_ratio: str = "1:1",
    return_url: bool = True
) -> str:
    """
    使用 Gemini VOD 生成图像并保存到指定路径。

    Args:
        prompt: 图像生成提示词，描述要生成的图像内容
        save_path: 生成的图片保存路径（如 /path/to/image.png）
        image_urls: 参考图片URL列表（可选）
        aspect_ratio: 图像宽高比，可选值：1:1, 16:9, 9:16, 4:3, 3:4

    Returns:
        结果信息，包含保存路径或错误信息
    """
    try:
        generator = GeminiVodImageGenerator()
        result = generator.generate(
            prompt=prompt,
            image=image_urls or [],
            aspect_ratio=aspect_ratio,
            return_url=return_url
        )

        if return_url:
            return f"生成的图片url是:{result}"

        if result.get("status") == "SUCCESS" and result.get("image_data"):
            # 保存图片
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(result["image_data"])
            return f"图片生成成功，已保存到 {save_path}"
        else:
            error = result.get("error", "未知错误")
            return f"图片生成失败: {error}"

    except Exception as e:
        return f"图片生成异常: {str(e)}"

