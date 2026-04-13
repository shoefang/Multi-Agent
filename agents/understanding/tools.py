"""
tools
"""

import json
import json
import re
import base64
import requests
import time
from pathlib import Path
from utils.qwen_vl import image_understanding

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


# ============ 图像理解相关函数 ============

def parse_json(content: str) -> dict:
    """
    解析JSON格式的字符串，并返回一个Python对象。

    Args:
        content: JSON格式的字符串，可能包含前后的 ```json 和 ``` 标记。

    Returns:
        dict: 解析后得到的Python字典对象。
    """
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.replace("'", '"').replace("\n", "")
    try:
        return json.loads(content)
    except Exception as e:
        print(e)
        return {}


def Image_understanding(
    image_urls: list,
    brief: str = "",
):
    """
    请求VLM模型进行图像理解，分析图像内容并生成描述。
    """
    captions = image_understanding(image_urls, brief)
    return str(captions)




if __name__ == "__main__":
    result_dir = '/home/data/icode/baidu/miaobi/multi_agent/outputs/希思黎黑玫瑰面霜'
    prompt = "浴袍美女在森林中回眸"
    input_file = "/home/data/icode/baidu/miaobi/multi_agent/outputs/希思黎黑玫瑰面霜/plan.md"


