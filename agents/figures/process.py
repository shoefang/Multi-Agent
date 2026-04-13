"""
Planning Agent: 执行规划的agent
"""
import json
import os
import json
import re
import inspect
from pathlib import Path
from datetime import datetime
import agents.figures.tools as tools
import agents.figures.prompt as prompt
from utils.api import request_llm_v2


# ============================================================
# 1. 通用 Agent
# ============================================================

IMAGE_NUM = 0
class ImageAgent:
    """
    Planning Agent
    
    工作流程：
    1. 接收用户请求
    2. 判断是否需要 Skill（如果用户提到 /skill-name 或需要特定能力）
    3. 发现并加载合适的 Skill
    4. 按照 Skill 指令执行
    """
    
    def __init__(self, 
                model: str="deepseek-v3.2", 
                skills_dir: str="skills/", 
                schema_dir: str="tools_schema.json",
                blacklist: str="./configs/sensitive_blacklist.json",
                audience: str="大众读者",
                language: str="中文",
                aspect_ratio: str="1:1",
                save_dir: str="/home/data/icode/agent_template/output"
                ):
        BASE_DIR = Path(__file__).parent
        # 加载工具
        self.TOOL_FUNCTIONS = {
            name: func
            for name, func in inspect.getmembers(tools, inspect.isfunction)
            if func.__module__ == tools.__name__   # 只保留 tools.py 中定义的函数
        }
        with open(os.path.join(BASE_DIR, schema_dir), "r") as f:
            self.TOOLS_SCHEMA = json.load(f)
        # self._check_tools()
        self.save_dir = save_dir
        self.blacklist_dir = blacklist

        self.model = model
        self.skills_dir = os.path.join(BASE_DIR, skills_dir)
        self.audience = audience
        self.language = language
        self.aspect_ratio = aspect_ratio

        self.messages = []
        self.max_turns = 100
        self.current_skill = None  # 动态加载的 Skill
    
    def _get_base_system_prompt(self) -> str:
        """
        通用的 System Prompt - 这是 Agent 的基础能力
        注意：这里不包含任何具体 Skill 的指令
        """
        return prompt.SYSTEM_PROMPT.format(skills_dir=self.skills_dir)

    def _get_format_user_prompt(self, user_input: str, planning: str, task_type: str) -> str:
        user_prompt = prompt.TEMPLATE_PROMPT.format(
            user_input=user_input,
            planning=planning,
            task_type=task_type,
            aspect_ratio=self.aspect_ratio,
            audience=self.audience,
            language=self.language,
            save_dir=f"{self.save_dir}/figure.md"
        )
        return user_prompt

    def run(self, user_input: str, planning: str, task_type: str, task_id: str="0") -> str:
        """
        执行用户请求
        """
        user_request = self._get_format_user_prompt(user_input, planning, task_type)
        print(f"🚀 收到请求: {user_input}...")
        
        # 检查是否直接触发 Skill（如 /baoyu-infographic）【然鹅，并没有直接触发】
        skill_match = re.match(r'^/(\S+)', user_request)
        if skill_match:
            skill_name = skill_match.group(1)
            print(f"📦 检测到 Skill 触发: {skill_name}")
        
        # 初始化消息
        self.messages = [
            {"role": "system", "content": self._get_base_system_prompt()},
            {"role": "user", "content": user_request}
        ]
        
        for turn in range(self.max_turns):
            print(f"\n--- Turn {turn + 1} ---")
            
            response = request_llm_v2(
                prompt=None,
                messages=self.messages,
                tools=self.TOOLS_SCHEMA,
                model_name=self.model
            )
            
            if not response or "choices" not in response:
                print("❌ LLM 调用失败")
                return "LLM 调用失败"

            # print(response)
            # exit()
            
            choice = response["choices"][0]
            message = choice["message"]
            if "tool_calls" in message and message["tool_calls"]:
                self.messages.append(message) # 把tool_calls加进来了
                
                for tool_call in message["tool_calls"]:
                    result = self._execute_tool(tool_call) 
                    
                    # 检查是否是 complete_task 工具调用【LLM不能自己关闭python程序，如果Agent认为任务完成了，就调用complete_task】
                    func_name = tool_call["function"]["name"]
                    if func_name == "complete_task":
                        # 解析完成结果
                        if result.startswith(tools.TASK_COMPLETE_SIGNAL):
                            final_result = json.loads(result[len(tools.TASK_COMPLETE_SIGNAL):])
                            print("\n✅ 任务已通过 complete_task 工具正式完成")
                            print(f"📋 摘要: {final_result['summary']}")
                            if final_result.get('files_created'):
                                print(f"📁 创建的文件: {final_result['files_created']}")
                            return final_result['summary']
                    
                    if func_name == "load_skill": # _execute_tool中已经完成了
                        print("📖 Skill 指令已加载到上下文")
                    
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result if not result.startswith(tools.TASK_COMPLETE_SIGNAL) else "任务已完成"
                    })
            else:
                content = message.get("content", "")
                print(f"🤖 Agent: {content[:200]}...")
                self.messages.append(message)
            os.makedirs(f"{self.save_dir}/figures_log", exist_ok=True)
            with open(f"{self.save_dir}/figures_log/{task_id}_{turn}.json", "w") as f:
                f.write(json.dumps(self.messages, indent=True, ensure_ascii=False))
        return "达到最大轮次限制"
    
    def _execute_tool(self, tool_call: dict) -> str:
        """执行工具调用"""
        func_name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]
        
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return f"参数解析失败: {args_str}"
        
        print(f"🔧 {func_name}({json.dumps(args, ensure_ascii=False)[:100]}...)")

        
        if func_name in self.TOOL_FUNCTIONS:
            try:
                result = self.TOOL_FUNCTIONS[func_name](**args)
                # 截断长结果的显示
                display = result[:200] + "..." if len(result) > 200 else result
                print(f"   → {display}")
                return result
            except Exception as e:
                return f"执行错误: {str(e)}"
        
        return f"未知工具: {func_name}"
    
    def _handle_user_interaction(self, ask_data: dict) -> str:
        """处理用户交互，在终端显示问题并等待输入"""
        header = ask_data.get("header", "问题")
        question = ask_data["question"]
        options = ask_data.get("options")
        
        print(f"\n{'=' * 50}")
        print(f"💬 [{header}] {question}")
        print("=" * 50)
        
        if options:
            # 显示选项
            for i, opt in enumerate(options, 1):
                label = opt.get("label", "")
                desc = opt.get("description", "")
                if desc:
                    print(f"  {i}. {label}")
                    print(f"     {desc}")
                else:
                    print(f"  {i}. {label}")
            print()
            
            # 等待用户选择
            while True:
                try:
                    choice = input("请输入选项编号 (或直接输入内容): ").strip()
                    if choice.isdigit():
                        idx = int(choice) - 1
                        if 0 <= idx < len(options):
                            selected = options[idx]["label"]
                            print(f"✓ 已选择: {selected}\n")
                            return selected
                        else:
                            print(f"请输入 1-{len(options)} 之间的数字")
                    else:
                        # 用户直接输入内容
                        print(f"✓ 输入: {choice}\n")
                        return choice
                except KeyboardInterrupt:
                    print("\n⚠️ 用户取消")
                    return "取消"
        else:
            # 自由输入
            answer = input("请输入: ").strip()
            print(f"✓ 输入: {answer}\n")
            return answer


# ============================================================
# 3. 使用示例
# ============================================================
if __name__ == "__main__":
    # 初始化 PlanningAgent
    agent = ImageAgent(
        model="kimi-k2.5",                # 使用的模型
        skills_dir="skills/",                # 技能存放目录
        schema_dir="/home/data/icode/agent_template/tools_schema.json",       # 工具 schema 文件 
        audience="大众读者",                   # 目标读者
        language="中文",                       # 输出语言
        aspect_ratio="16:9"                    # 默认宽高比（用于图文生成）
    )
    

    input_md = "/home/data/icode/agent_template/input/iPhone.md"
    #input_md = "/home/data/icode/agent_template/input/丹媚和金毓婷哪个好.md"

    # 读取 md 文件内容
    with open(input_md, "r", encoding="utf-8") as f:
        content = f.read()


    query = 'iPhone 17系列深度测评：十年数码博主眼中的真实升级与取舍'
    save_dir = f"/home/data/icode/agent_template/output/iPhone"
    os.makedirs(save_dir, exist_ok=True)
    agent.save_dir = save_dir
    query_class = ""
    #query_class = "outline配图"
    
    output = agent.run(query, content, query_class)