"""
tools
"""

import json
import re
from pathlib import Path
from utils.ref_reader import ref_reader



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

def search_docs(query: str, display: int = 1, undisplay: int = 2, site: str = "") -> str:
    """
    从全网搜索信息

    Args:
        query: 搜索词
        display: 来源为display的检索内容数量（权威媒体、专业网站）
        undisplay: 来源为undisplay的检索内容数量（小红书、抖音等UGC）
        site: 指定网站域名（可选）

    Returns:
        检索结果文本
    """
    try:
        result_content = ref_reader(query, display, undisplay, site=[] if not site else [site])
        return str(result_content)
    except Exception as e:
        print(f"检索错误: {str(e)}")
        return f"检索失败: {str(e)}"