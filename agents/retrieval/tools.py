"""
tools
"""

import json
import re
from pathlib import Path
from datetime import datetime

from utils.ref_reader import ref_reader
from utils.api import request_llm_v2, parse_json
import agents.retrieval.prompt as prompt


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


def search_docs(query: str, display: int = 1, undisplay: int = 3, site: str = "") -> str:
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
        return result_content
    except Exception as e:
        print(f"检索错误: {str(e)}")
        return f"检索失败: {str(e)}"


def evaluate_complexity(query: str, model: str = "deepseek-v3.2") -> str:
    """评估 query 复杂度并返回 JSON 字符串。"""
    eval_prompt = prompt.COMPLEXITY_EVALUATION_PROMPT.format(query=query)
    response = request_llm_v2(
        prompt=eval_prompt,
        model_name=model,
        messages=None,
        tools=None
    )

    default_result = {
        "complexity_level": 3,
        "dimensions": ["信息收集"],
        "estimated_rounds": 3,
        "max_rounds_suggestion": 5,
        "reasoning": "复杂度评估失败，使用默认值"
    }

    if not response or "choices" not in response or not response["choices"]:
        return json.dumps(default_result, ensure_ascii=False)

    content = response["choices"][0].get("message", {}).get("content", "")
    parsed = parse_json(content)
    if not isinstance(parsed, dict):
        return json.dumps(default_result, ensure_ascii=False)

    return json.dumps(parsed, ensure_ascii=False)


def generate_expanded_queries(
    query: str,
    collected_info: str = "",
    current_round: int = 1,
    used_queries=None,
    expansion_direction: str = "auto",
    model: str = "deepseek-v3.2"
) -> str:
    """生成扩展检索词并返回 JSON 字符串。"""
    if used_queries is None:
        used_queries = []

    if isinstance(used_queries, list):
        used_queries_text = ", ".join(used_queries) if used_queries else "暂无"
    else:
        used_queries_text = str(used_queries) if used_queries else "暂无"

    gen_prompt = prompt.EXPAND_QUERIES_PROMPT.format(
        query=query,
        current_round=current_round,
        collected_info_summary=collected_info or "暂无已收集信息",
        used_queries=used_queries_text,
        expansion_direction=expansion_direction
    )

    response = request_llm_v2(
        prompt=gen_prompt,
        model_name=model,
        messages=None,
        tools=None
    )

    default_result = {
        "round_number": current_round,
        "expansion_type": "vertical",
        "queries": [query],
        "focus": "基础信息收集",
        "reasoning": "扩展检索词生成失败，回退到原始query"
    }

    if not response or "choices" not in response or not response["choices"]:
        return json.dumps(default_result, ensure_ascii=False)

    content = response["choices"][0].get("message", {}).get("content", "")
    parsed = parse_json(content)
    if not isinstance(parsed, dict):
        return json.dumps(default_result, ensure_ascii=False)

    return json.dumps(parsed, ensure_ascii=False)


def evaluate_information_gain(
    previous_info: str,
    new_info: str,
    core_dimensions,
    model: str = "deepseek-v3.2"
) -> str:
    """评估信息增益并返回 JSON 字符串。"""
    if isinstance(core_dimensions, list):
        core_dimensions_text = ", ".join(core_dimensions)
    else:
        core_dimensions_text = str(core_dimensions) if core_dimensions else "信息收集"

    eval_prompt = prompt.INFO_GAIN_EVALUATION_PROMPT.format(
        previous_info=previous_info or "这是第一轮检索",
        new_info=new_info,
        core_dimensions=core_dimensions_text
    )

    response = request_llm_v2(
        prompt=eval_prompt,
        model_name=model,
        messages=None,
        tools=None
    )

    default_result = {
        "new_info_score": 0.5,
        "covered_dimensions": [],
        "missing_dimensions": core_dimensions if isinstance(core_dimensions, list) else [],
        "quality_assessment": "信息增益评估失败，使用默认值",
        "continue_search": True,
        "reasoning": "评估失败，建议继续检索"
    }

    if not response or "choices" not in response or not response["choices"]:
        return json.dumps(default_result, ensure_ascii=False)

    content = response["choices"][0].get("message", {}).get("content", "")
    parsed = parse_json(content)
    if not isinstance(parsed, dict):
        return json.dumps(default_result, ensure_ascii=False)

    return json.dumps(parsed, ensure_ascii=False)


def _sanitize_log_filename(name: str) -> str:
    """将字符串清洗为安全文件名片段。"""
    cleaned = re.sub(r"[^\w\-\u4e00-\u9fff]+", "_", str(name or ""))
    return cleaned.strip("_") or "unknown"


def _save_sub_skill_context(messages: list, step_logs: list, query: str, skill_name: str, status: str, round_number: int = None):
    """保存 run_sub_skill 的完整执行上下文。支持多轮次合并存储。"""
    log_dir = Path("./retrieval_log") / "sub_skill"
    log_dir.mkdir(parents=True, exist_ok=True)

    safe_skill_name = _sanitize_log_filename(skill_name)
    log_path = log_dir / f"sub_skill_context_{safe_skill_name}.json"

    # 构建当前轮次的数据
    current_round_data = {
        "round_number": round_number,
        "status": status,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_steps": len(step_logs),
        "step_logs": step_logs,
        "messages": messages
    }

    # 如果有 round_number，使用多轮次格式存储
    if round_number is not None:
        # 读取现有数据
        existing_data = {"query": query, "skill_name": skill_name, "rounds": []}
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    if "rounds" not in existing_data:
                        existing_data["rounds"] = []
            except Exception:
                existing_data = {"query": query, "skill_name": skill_name, "rounds": []}

        # 更新或追加当前轮次
        round_updated = False
        for i, r in enumerate(existing_data.get("rounds", [])):
            if r.get("round_number") == round_number:
                existing_data["rounds"][i] = current_round_data
                round_updated = True
                break

        if not round_updated:
            existing_data["rounds"].append(current_round_data)

        # 按 round_number 排序
        existing_data["rounds"].sort(key=lambda x: x.get("round_number", 0) or 0)

        # 更新最后修改时间和整体状态
        existing_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing_data["total_rounds"] = len(existing_data["rounds"])

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
    else:
        # 无 round_number 时，使用原有格式（单次存储）
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "query": query,
                "skill_name": skill_name,
                "status": status,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_steps": len(step_logs),
                "step_logs": step_logs,
                "messages": messages
            }, f, ensure_ascii=False, indent=2)


def run_sub_skill(
    skill_name: str,
    context_json: str,
    query: str,
    max_steps: int = 100,
    model: str = "deepseek-v3.2"
) -> str:
    """
    运行一个 Phase 级子 Agent。

    加载 skills/phases/{skill_name}/SKILL.md 作为 system prompt，
    以 context_json 作为 user 消息，启动独立的 tool-calling 循环。
    子 Agent 拥有完全隔离的 messages 上下文，不污染主 Agent。
    当子 Agent 调用 complete_task 时，返回其 payload JSON 字符串。

    Args:
        skill_name:    子 Skill 目录名，如 "01_复杂度评估"
        context_json:  传给子 Agent 的输入，JSON 字符串
        query:         当前主任务 query，用于日志归档
        max_steps:     子 Agent 最大执行步数兜底阈值（防止异常失控）
        model:         LLM 模型名

    Returns:
        子 Agent 的 complete_task payload JSON 字符串；
        出错时返回包含 "error" 字段的 JSON 字符串。
    """
    import inspect
    import sys
    _self = sys.modules[__name__]

    query = (query or "").strip()
    if not query:
        return json.dumps({"error": "query is required for run_sub_skill"}, ensure_ascii=False)

    step_logs = []

    BASE_DIR = Path(__file__).parent
    skill_path = BASE_DIR / "skills" / "phases" / skill_name / "SKILL.md"
    if not skill_path.exists():
        return json.dumps({"error": f"Sub-skill not found: {skill_path}"}, ensure_ascii=False)

    system_prompt = skill_path.read_text(encoding="utf-8")

    schema_path = BASE_DIR / "tools_schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        raw_tools_schema = json.load(f)

    # 子 Agent 禁止再调用 run_sub_skill，避免递归套娃
    tools_schema = [
        item for item in raw_tools_schema
        if item.get("function", {}).get("name") != "run_sub_skill"
    ]

    tool_functions = {
        name: func
        for name, func in inspect.getmembers(_self, inspect.isfunction)
        if func.__module__ == _self.__name__ and name != "run_sub_skill"
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_json}
    ]

    # 针对 Phase 2（动态检索），解析并显示当前轮次信息
    round_number = None
    max_rounds_hint = None
    if skill_name == "02_动态检索与增益评估":
        parsed_context = {}
        if isinstance(context_json, str):
            try:
                parsed_context = json.loads(context_json)
            except Exception:
                parsed_context = {}
        elif isinstance(context_json, dict):
            parsed_context = context_json

        round_number = parsed_context.get("round_number")
        max_rounds_hint = parsed_context.get("max_rounds")

        # 显示轮次信息
        if round_number is not None and max_rounds_hint is not None:
            print(f"\n{'='*50}")
            print(f"  第 {round_number}/{max_rounds_hint} 轮检索")
            print(f"{'='*50}")
        elif round_number is not None:
            print(f"\n  第 {round_number} 轮检索")

    # 其他 skill 只显示简单开始信息
    else:
        print(f"\n[{skill_name}] 执行中...")

    for step in range(1, max_steps + 1):
        response = request_llm_v2(
            prompt=None,
            model_name=model,
            messages=messages,
            tools=tools_schema
        )
        if not response or "choices" not in response or not response["choices"]:
            error_result = json.dumps({"error": f"sub-skill LLM call failed"}, ensure_ascii=False)
            _save_sub_skill_context(messages, step_logs, query, skill_name, status="error", round_number=round_number)
            print(f"[{skill_name}] LLM调用失败")
            return error_result

        message = response["choices"][0].get("message", {})
        tool_calls = message.get("tool_calls") or []

        assistant_msg = {"role": "assistant", "content": message.get("content", "")}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        if not tool_calls:
            content = message.get("content", "")
            if content.startswith(TASK_COMPLETE_SIGNAL):
                payload_str = content[len(TASK_COMPLETE_SIGNAL):]
                _save_sub_skill_context(messages, step_logs, query, skill_name, status="completed", round_number=round_number)
                return payload_str

            _save_sub_skill_context(messages, step_logs, query, skill_name, status="stopped", round_number=round_number)
            return content

        for tool_call in tool_calls:
            func_name = tool_call.get("function", {}).get("name", "")
            raw_args = tool_call.get("function", {}).get("arguments", "{}")
            try:
                args = json.loads(raw_args)
                args_preview = json.dumps(args, ensure_ascii=False)
            except Exception:
                args = {}
                args_preview = str(raw_args)

            if func_name == "run_sub_skill":
                result = "执行错误: 子 Agent 不允许调用 run_sub_skill（已阻断递归）"
            elif func_name in tool_functions:
                try:
                    result = tool_functions[func_name](**args)
                except Exception as e:
                    result = f"执行错误: {e}"
            else:
                result = f"未知工具: {func_name}"

            try:
                result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            except Exception:
                result_str = str(result)

            result_preview = result_str

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": result_str
            })

            step_logs.append({
                "step": step,
                "tool": func_name,
                "args_preview": args_preview,
                "result_preview": result_preview,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            _save_sub_skill_context(messages, step_logs, query, skill_name, status="running", round_number=round_number)

            if result_str.startswith(TASK_COMPLETE_SIGNAL):
                payload_str = result_str[len(TASK_COMPLETE_SIGNAL):]
                _save_sub_skill_context(messages, step_logs, query, skill_name, status="completed", round_number=round_number)
                return payload_str

    timeout_result = json.dumps({"error": f"sub-skill '{skill_name}' exceeded max_steps"}, ensure_ascii=False)
    _save_sub_skill_context(messages, step_logs, query, skill_name, status="error", round_number=round_number)
    print(f"[{skill_name}] 超出最大步数限制")
    return timeout_result


# 特殊标记：用于 complete_task 工具的返回值
TASK_COMPLETE_SIGNAL = "__TASK_COMPLETE__"


def complete_task(summary: str, files_created: list = None) -> str:
    """
    标记任务完成并退出 Agent 循环。
    这是唯一正确的退出方式。
    
    Args:
        summary: 任务完成摘要
        files_created: 创建的文件路径列表
    
    Returns:
        包含特殊标记的结果JSON
    """
    result = {
        "status": "completed",
        "summary": summary,
        "files_created": files_created or []
    }
    return TASK_COMPLETE_SIGNAL + json.dumps(result, ensure_ascii=False)