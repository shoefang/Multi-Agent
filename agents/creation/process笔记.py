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

import agents.creation.tools as tools
import agents.creation.prompt as prompt
from utils.api import request_llm_v2

# ============================================================
# 1. 通用 Agent
# ============================================================
class CreationAgent:
    """
    Creation Agent
    
    工作流程：
    1. 接收用户请求
    2. 判断是否需要 Skill（如果用户提到 /skill-name 或需要特定能力）
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

    def _get_format_user_prompt(self, outline="", user_input="", task_type=""):
        user_prompt = prompt.TEMPLATE_PROMPT.format(
            task_type=task_type,
            user_input=user_input,
            outline=outline,
            skill_dir=self.skills_dir,
            save_dir=f"{self.save_dir}"
        )
        return user_prompt

    def run(self, outline: str, user_input: str, task_type: str="商单图文") -> str:
        """
        执行用户请求
        """
        user_request = self._get_format_user_prompt(outline, user_input, task_type)
        print(f"🚀 收到请求: {outline[:20]}...")
        
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
                    if func_name == "complete_task":
                        # 解析完成结果
                        if result.startswith(tools.TASK_COMPLETE_SIGNAL):
                            final_result = json.loads(result[len(tools.TASK_COMPLETE_SIGNAL):])
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
                        "content": result if not result.startswith(tools.TASK_COMPLETE_SIGNAL) else "调用工具已完成"
                    })
            else:
                content = message.get("content", "")
                print(f"🤖 Agent（调用LLM结果）: {content[:200]}...")
                if content == "":
                    print(f"\nLLM结果为空。原始响应是:{response}")
                # print(f"🤖 Agent: {content[:200]}...")
                self.messages.append(message)
            
            # 保存Agent轮次执行结果
            filename = re.sub(r'[^\w\s-]', '', outline).strip()[:20] or 'unnamed'
            os.makedirs(f"{self.save_dir}/creation_log", exist_ok=True)
            with open(f"{self.save_dir}/creation_log/{filename}_{turn}.json", "w") as f:
                f.write(json.dumps(self.messages, indent=True, ensure_ascii=False))
        return "达到最大轮次限制"
    
    def _execute_tool(self, tool_call: dict) -> str:
        """执行工具调用"""
        func_name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]
        
        try:
            args = json.loads(args_str)
            print(f"   → 开始调用{func_name}方法, 参数:{args_str[:500]}")
        except json.JSONDecodeError:
            return f"参数解析失败: {args_str}"
        
        # print(f"🔧 {func_name}({json.dumps(args, ensure_ascii=False)[:100]}...)")
        
        if func_name in self.TOOL_FUNCTIONS:
            try:
                result = self.TOOL_FUNCTIONS[func_name](**args)
                display = result[:200] + "..." if len(result) > 200 else result
                # # 截断长结果的显示
                # display = result[:200] + "..." if len(result) > 200 else result
                print(f"   → 调用{func_name}方法结果:\n{display}")
                return result
            except Exception as e:
                return f"执行错误: {str(e)}"
        
        return f"未知工具（方法): {func_name}"
    
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
    current_working_dir = os.getcwd()
    print(f"当前工作目录: {current_working_dir}")
    #project_dir = "/home/data/icode/baidu/miaobi/multi_agent/agents/creation"
    project_dir = "/home/data/zhonglong/icode/baidu/miaobi/multi_agent/agents/creation"
    save_name = "笔记_0330_11_肥胖"
    #save_dir = f"/home/data/icode/baidu/miaobi/multi_agent/outputs/{save_name}"
    save_dir = f"/home/data/zhonglong/icode/baidu/miaobi/multi_agent/outputs/{save_name}"
    os.makedirs(save_dir, exist_ok=True)

    # 1. 初始化 Agent
    # 注意：确保你的 api.py 已经配置好了 API Key
    agent = CreationAgent(
        model="deepseek-v3.2",
        audience="大众",
        language="中文",
        save_dir=save_dir
    )

    user_input = {
        "user_demand": """标题：无。正文：肥肉脂肪最怕你做这几件事，快来看看你犯了没有""",
        "outline": "",
        "images": ['http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859156088511_2rv7xi7k.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A25%3A59Z%2F-1%2F%2F9b13f21588054a12f6893cc4194ebed7edb180441d97009ba45e572a5f53d73e', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859152260582_666oib23.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A25%3A55Z%2F-1%2F%2F56c68ec786312755b093787dcadb50b1307aada03a21ebd9290d8407042026f3', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859160633659_zh9ulknx.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A26%3A03Z%2F-1%2F%2F29b546ec05a09f3f07b5ac2865270ec2eb55eab3646511101021190847c7e982', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859148448273_qfsggb22.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A25%3A51Z%2F-1%2F%2F288451d180e2713ff133554c89e676d1c23f1f070d8ceabd2b2730a674adbef8', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859159895693_4pp4mne0.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A26%3A00Z%2F-1%2F%2Fcf85bc096345fc1060633b95f7e0a87f0b041df5eb33f8a5a44abe661f5c05cd'],
        "reference": ""
    }

    # 3. 运行 Agent
    print("--- 任务开始 ---")
    final_summary = agent.run(
        outline="",
        user_input=user_input,
        task_type="lite笔记"
    )
    
    print("\n--- 最终执行结果 ---")
    print(final_summary)



"""
肥肉脂肪最怕你做这几件事，快来看看你犯了没有

['http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859156088511_2rv7xi7k.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A25%3A59Z%2F-1%2F%2F9b13f21588054a12f6893cc4194ebed7edb180441d97009ba45e572a5f53d73e', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859152260582_666oib23.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A25%3A55Z%2F-1%2F%2F56c68ec786312755b093787dcadb50b1307aada03a21ebd9290d8407042026f3', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859160633659_zh9ulknx.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A26%3A03Z%2F-1%2F%2F29b546ec05a09f3f07b5ac2865270ec2eb55eab3646511101021190847c7e982', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859148448273_qfsggb22.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A25%3A51Z%2F-1%2F%2F288451d180e2713ff133554c89e676d1c23f1f070d8ceabd2b2730a674adbef8', 'http://miaobi-platform-ads-video.bj.bcebos.com/miaobi-platform-ads-video/sponsored_post/1774859159895693_4pp4mne0.png?authorization=bce-auth-v1%2FALTAK1ABTKFBCsCZZyPgEESk8l%2F2026-03-30T08%3A26%3A00Z%2F-1%2F%2Fcf85bc096345fc1060633b95f7e0a87f0b041df5eb33f8a5a44abe661f5c05cd']

"""