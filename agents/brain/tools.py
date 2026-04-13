"""
tools
"""

import json
import os
import re
from pathlib import Path
from agents.retrieval.process import DeepCollectAgent
from agents.planning.process import PlanningAgent
from agents.figures.process import ImageAgent
from agents.creation.process import CreationAgent
from agents.understanding.process import UnderstandingAgent



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

def understanding(user_input: str, task_type: str = "通用图文", save_dir: str = "./outputs") -> str:
    """
    执行输入理解Agent，对用户输入进行深度分析。

    Args:
        user_input: 用户输入的文本和图像信息
        task_type: 任务类型，如 "通用图文"、"笔记" 等
        save_dir: 结果保存目录

    Returns:
        理解分析结果
    """
    try:
        agent = UnderstandingAgent(
            model="deepseek-v3.2",
            audience="大众",
            language="中文",
            save_dir=save_dir
        )
        result = agent.run(user_input, task_type)
        understanding_dir = f"{save_dir}/understanding.md" 
        return f"输入理解完成: {understanding_dir}"
    except Exception as e:
        return f"输入理解异常: {str(e)}"


def planning(query: str, understanding: str, task_type: str = "通用图文", save_dir: str = "./outputs") -> str:
    """
    执行规划Agent，生成内容大纲和需求。

    Args:
        query: 用户查询/需求
        understanding: 输入理解结果
        task_type: 任务类型
        save_dir: 结果保存目录

    Returns:
        规划结果
    """
    try:
        os.makedirs(save_dir, exist_ok=True)

        agent = PlanningAgent(
            model="deepseek-v3.2",
            audience="大众",
            language="中文",
            save_dir=save_dir
        )
        result = agent.run(query, understanding, task_type)
        plan_dir = f"{save_dir}/plan.md" 
        return f"规划生成完成: {plan_dir}"
    except Exception as e:
        return f"规划生成异常: {str(e)}"


def collect(query: str, max_rounds: int = 20, save_dir: str = "./outputs") -> str:
    """
    执行信息收集Agent，从全网检索相关信息。

    Args:
        query: 检索查询
        max_rounds: 最大轮次
        save_dir: 结果保存目录

    Returns:
        收集结果
    """
    try:
        agent = DeepCollectAgent(max_rounds=max_rounds, save_dir=save_dir)
        result = agent.run_skill(query=query, max_steps=42)
        info_dir = f"{save_dir}/report.md"
        return f"信息收集完成: {info_dir}"
    except Exception as e:
        return f"信息收集异常: {str(e)}"

def generate_figures(understanding: str, plan: str, task_type: str = "通用图文", aspect_ratio: str = "16:9", save_dir: str = "./outputs") -> str:
    """
    执行配图生成Agent，为内容生成配图。

    Args:
        understanding: 输入理解结果
        outline: 内容大纲
        task_type: 任务类型
        aspect_ratio: 图像宽高比
        save_dir: 结果保存目录

    Returns:
        配图生成结果
    """
    try:
        agent = ImageAgent(
            model="deepseek-v3.2",
            aspect_ratio=aspect_ratio,
            save_dir=save_dir
        )
        os.makedirs(f"{save_dir}/figures", exist_ok=True)
        result = agent.run(understanding, plan, task_type)
        figure_dir = f"{save_dir}/figure.md"
        return f"配图生成完成: {figure_dir}"
    except Exception as e:
        return f"配图生成异常: {str(e)}"

def create(plan: str, understanding: str, info: str, figure: str, task_type: str = "通用图文", save_dir: str = "./outputs") -> str:
    """
    执行创作Agent，生成最终图文内容。

    Args:
        plan: 内容大纲
        user_input: 用户输入理解结果
        task_type: 任务类型
        save_dir: 结果保存目录

    Returns:
        创作结果
    """
    try:
        agent = CreationAgent(
            model="deepseek-v3.2",
            audience="大众",
            language="中文",
            save_dir=save_dir
        )
        plan += "\n [检索信息] \n" + info + "\n [配图] \n" + figure
        result = agent.run(
            outline=plan,
            user_input=understanding,
            task_type=task_type
        )
        create_dir = f"{save_dir}/article.md" 

        return f"内容创作完成: {create_dir}"
    except Exception as e:
        return f"内容创作异常: {str(e)}"


