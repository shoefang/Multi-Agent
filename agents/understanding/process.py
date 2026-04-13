"""
Creation Agent: 创造agent
"""
import json
import sys
import os
import json
import re
from pathlib import Path
import inspect
from datetime import datetime

import agents.understanding.tools as tools
import agents.understanding.prompt as prompt
from utils.api import request_llm_v2

# ============================================================
# 1. 通用 Agent
# ============================================================
class UnderstandingAgent:
    """
    Understanding Agent
    
    工作流程：
    1. 接收用户请求
    2. 理解用户意图
    3. 发现并加载合适的 Skill
    4. 按照 Skill 指令执行
    """
    
    def __init__(self, 
                model: str="deepseek-v3.2", # deepseek-v3、Kimi-K2.5
                skills_dir: str="skills", 
                schema_dir: str="tools_schema.json",
                blacklist: str="./configs/sensitive_blacklist.json",
                audience: str="大众读者",
                language: str="中文",
                aspect_ratio: str="1:1",
                save_dir: str='./'
                ):
        BASE_DIR = Path(__file__).parent
        # 加载工具, 从tools.py文件中加载
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
        print("self.skills_dir: ", self.skills_dir)
        self.audience = audience
        self.language = language
        self.aspect_ratio = aspect_ratio

        self.messages = []
        # TODO 最大轮次
        self.max_turns = 20
        self.current_skill = None  # 动态加载的 Skill
    
    def _get_base_system_prompt(self) -> str:
        """
        通用的 System Prompt - 这是 Agent 的基础能力
        注意：这里不包含任何具体 Skill 的指令
        """
        return prompt.SYSTEM_PROMPT.format(skills_dir=self.skills_dir, )

    def _get_format_user_prompt(self, user_input, task_type):
        user_prompt = prompt.TEMPLATE_PROMPT.format(
            task_type=task_type,
            user_input=user_input,
            language=self.language,
            skill_dir=self.skills_dir,
            save_dir=f"{self.save_dir}/understanding.md"
        )
        return user_prompt

    def run(self, user_input, task_type) -> str:
        """
        执行用户请求
        """
        user_request = self._get_format_user_prompt(user_input, task_type)
        print(f"🚀 收到请求: {user_input[:20]}...")
        
        # # 检查是否直接触发 Skill（如 /baoyu-infographic）
        # skill_match = re.match(r'^/(\S+)', user_request)
        # if skill_match:
        #     skill_name = skill_match.group(1)
        #     print(f"显示触发 Skill : {skill_name}")
        #     print(f"📦 检测到 Skill 触发: {skill_name}")
        
        # 初始化消息
        self.messages = [
            {"role": "system", "content": self._get_base_system_prompt()},
            {"role": "user", "content": user_request}
        ]
        
        # 调用Agent轮次
        for turn in range(self.max_turns):
            print(f"\n--- Turn {turn + 1} ---")
            
            # 调用语言模型
            response = request_llm_v2(
                prompt=None,
                messages=self.messages,
                tools=self.TOOLS_SCHEMA,
                model_name=self.model
            )

            # print(f"\n大模型响应是:{response}\n")
            
            if not response or "choices" not in response:
                print("❌ LLM 调用失败")
                return "LLM 调用失败"
            
            message = response["choices"][0]["message"]
            # 看 LLM 回来的是普通文本还是 tool_call
            if message.get("tool_calls"):
                self.messages.append(message)
                
                for tool_call in message["tool_calls"]:
                    result = self._execute_tool(tool_call)
                    
                    # 检查是否是 complete_task 工具调用
                    func_name = tool_call["function"]["name"]
                    # 将 result 转为字符串处理
                    result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                    if func_name == "complete_task":
                        # 解析完成结果
                        if result_str.startswith(tools.TASK_COMPLETE_SIGNAL):
                            final_result = json.loads(result_str[len(tools.TASK_COMPLETE_SIGNAL):])
                            print("\n✅ 任务已通过 complete_task 工具正式完成")
                            print(f"📋 摘要: {final_result['summary']}")
                            if final_result.get('files_created'):
                                print(f"📁 创建的文件: {final_result['files_created']}")
                            return final_result['summary']

                    if func_name == "load_skill":
                        print("📖 Skill 指令已加载到上下文")
                        # print(f"其他详细信息:{message}")

                    # TODO 当前每次message都会累加之前的消息，后续可考虑优化。如只添加增量内容的摘要
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result_str if not result_str.startswith(tools.TASK_COMPLETE_SIGNAL) else "调用工具已完成"
                    })
            else:
                content = message.get("content", "")
                print(f"🤖 Agent（调用LLM结果）: {content[:200]}...")
                if content == "":
                    print(f"\nLLM结果为空。原始响应是:{response}")
                # print(f"🤖 Agent: {content[:200]}...")
                self.messages.append(message)
            
            # 保存Agent轮次执行结果
            filename = re.sub(r'[^\w\s-]', '', user_input).strip()[:20] or 'unnamed'
            os.makedirs(f"{self.save_dir}/understanding_log", exist_ok=True)
            with open(f"{self.save_dir}/understanding_log/{filename}_{turn}.json", "w") as f:
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
                # 处理可能返回 list 或其他非字符串类型的结果
                if isinstance(result, str):
                    display = result[:200] + "..." if len(result) > 200 else result
                else:
                    result_str = json.dumps(result, ensure_ascii=False)
                    display = result_str[:200] + "..." if len(result_str) > 200 else result_str
                print(f"   → 调用{func_name}方法结果:{display}")
                return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            except Exception as e:
                return f"执行错误: {str(e)}"
        
        return f"未知工具: {func_name}"
    
    def _handle_user_interaction(self, ask_data: dict) -> str:
        """处理用户交互，在终端显示问题并等待输入"""
        header = ask_data.get("header", "问题")
        question = ask_data["question"]
        options = ask_data.get("options")
        
        print(f"\n{'='*50}")
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
    # 获取当前执行脚本的绝对路径目录，检查是否在项目目录下
    save_name = 'test'
    save_dir = f"/home/data/icode/baidu/miaobi/multi_agent/outputs/{save_name}"
    os.makedirs(save_dir, exist_ok=True)

    # 1. 初始化 Agent
    # 注意：确保你的 api.py 已经配置好了 API Key
    agent = UnderstandingAgent(
        model="deepseek-v3.2",
        audience="大众",
        language="中文",
        save_dir=save_dir
    )

    # 2. 准备输入数据
   
    images = {
        "image_1": {
        "url": "http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1773667569076111_ctzty3uu.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-16T13%3A26%3A09Z%2F-1%2F%2F2bf5dc5ee76da2260a94badc730d664dbed5b40f8731e96c883ddc54d3a3025c"
        },
        "image_2": {
        "url": "http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1773667569581491_xvipbcuu.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-16T13%3A26%3A12Z%2F-1%2F%2Fdc2bc5af4d0da45a966d2a7bea532f4efdcd7629f968596a4f92959595e2cc43"
        }
    }
    user_input = f"""
     找工作什么平台最可靠？
     【图像输入】
     {images} 
    """

    task_type = "笔记"

    # 3. 运行 Agent
    print("--- 任务开始 ---")
    final_summary = agent.run(
        user_input=user_input,
        task_type=task_type
    )
    
    print("\n--- 最终执行结果 ---")
    print(final_summary)
