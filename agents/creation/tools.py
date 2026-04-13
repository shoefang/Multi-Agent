"""
tools
"""

import json
import json
import re
import os
from pathlib import Path
from utils.generate_image_4 import Image2x2Generator
from utils.nano_banana_vod import GeminiVodImageGenerator
from utils.qwen_vl import image_understanding as image_understanding_api
from utils.upload_bos import upload_bos_image
from PIL import Image 

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
    # print(f"discover_skills的执行结果:{skills}")
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


def generate_image(
    input_file: str,
    result_dir: str
) -> str:
    """
    根据 outline.md 大纲生成四宫格信息图。

    Args:
        input_file: outline.md 大纲文件路径
        result_dir: 结果保存目录路径

    Returns:
        生成结果信息
    """
    import os
    try:
        # 读取大纲文件
        if not os.path.exists(input_file):
            return f"错误：大纲文件不存在 {input_file}"

        with open(input_file, "r", encoding="utf-8") as f:
            outline_md = f.read()

        # 创建输出目录
        os.makedirs(result_dir, exist_ok=True)

        # 生成图片
        generator = Image2x2Generator()
        results = generator.generate(outline_md, save_dir=result_dir)

        # 保存图片
        for idx, img in enumerate(results):
            # 生成文件名，例如 "image_0.jpg"
            filename = f"image_{idx}.jpg"
            filepath = os.path.join(result_dir, filename)
            img.save(filepath)
            print(f"Saved: {filepath}")

        # 返回结果
        return f"图片生成完成，共生成 {len(results)} 张图片，保存在 {result_dir}"

    except Exception as e:
        return f"图片生成异常: {str(e)}"


def generate_image_ref(
    prompt: str,
    save_path: str,
    image_urls: list = None,
    aspect_ratio: str = "3:4",
    return_url: bool = False

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
                return f"生成的图片url是:{result.get('image_url', '')}"
        
        # 如果返回的是 dict，按照原有逻辑处理
        if result.get("status") == "SUCCESS" and result.get("image_data"):
            # 保存图片
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(result["image_data"])
            
            return f"图片已保存到: {save_path}"
        else:
            error = result.get("error", "未知错误")
            return f"图片生成失败: {error}"

    except Exception as e:
        return f"图片生成异常: {str(e)}"

def list_skill_resources(skills_dir: str, skill_id: str) -> str:
    """
    扫描指定 Skill 目录下的所有子目录（styles/layouts等），并列出其中的配置文件名
    """
    skill_path = Path(skills_dir) / skill_id
    resources = {}

    if not skill_path.exists() or not skill_path.is_dir():
        return json.dumps({"error": f"Skill path {skill_id} not found."}, ensure_ascii=False)

    # 遍历 Skill 目录下的子目录
    for item in skill_path.iterdir():
        # 排除 SKILL.md 本身和隐藏文件夹，只看 styles, layouts 等子目录
        if item.is_dir() and not item.name.startswith('.'):
            # 获取该子目录下所有的 .txt 和 .md 文件名（去掉后缀）
            files = [f.stem for f in item.glob("*") if f.suffix in ['.txt', '.md']]
            if files:
                resources[item.name] = files
    
    return json.dumps(resources, ensure_ascii=False, indent=2)


def load_config(skills_dir: str, skill_id: str, config_type: str, config_name: str) -> str:
    """
    读取具体的配置文件内容
    """
    base_path = Path(skills_dir) / skill_id / config_type
    
    # 尝试读取 .txt 或 .md 后缀的文件
    for ext in ['.txt', '.md']:
        file_path = base_path / f"{config_name}{ext}"
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                return content
            except Exception as e:
                return f"Error reading file: {str(e)}"
    
    return f"Error: Configuration '{config_name}' not found in {config_type}."

def image_understanding(
    image_urls: list,
    brief: str = "",
):
    """
    请求VLM模型进行图像理解，分析图像内容并生成描述。
    """
    captions = image_understanding_api(image_urls, brief)
    return "图片理解结果：" + str(captions)



def upload_image(path):
    """
    上传本地图片到BOS云存储，返回图片的预签名URL。

    Args:
        path: 本地图片文件路径（如 /path/to/image.png）

    Returns:
        上传成功返回图片的预签名URL，失败返回错误信息
    """

    try:
        # 检查文件是否存在
        if not os.path.exists(path):
            return f"错误：文件不存在 {path}"

        # 检查文件是否为图片
        ext = os.path.splitext(path)[1].lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            return f"错误：不支持的图片格式 {ext}"

        # 打开图片
        image = Image.open(path)
        # 获取文件名
        filename = os.path.basename(path)

        # 上传到BOS
        url = upload_bos_image(image, filename)

        return f"图片上传成功，URL: {url}"

    except Exception as e:
        return f"图片上传异常: {str(e)}"
