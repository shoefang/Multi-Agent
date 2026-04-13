"""
Planning Agent: 执行规划的agent
"""
import json
import sys
import os
import json
import re
from pathlib import Path
import inspect
from datetime import datetime

import agents.planning.tools as tools
import agents.planning.prompt as prompt
from utils.api import request_llm_v2

# ============================================================
# 1. 通用 Agent
# ============================================================
class PlanningAgent:
    """
    Planning Agent
    
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

    def _get_format_user_prompt(self, query="", user_input="", task_type=""):
        user_prompt = prompt.TEMPLATE_PROMPT.format(
            task_type=task_type,
            user_input=user_input,
            skill_dir=self.skills_dir,
            save_dir=f"{self.save_dir}"
        )
        #save_dir=f"{self.save_dir}/plan.md"
        return user_prompt

    def run(self, query: str, user_input: str, task_type: str="商单图文") -> str:
        """
        执行用户请求
        """
        user_request = self._get_format_user_prompt(query, user_input, task_type)
        print(f"🚀 收到请求: {query}...")
        
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
                        if isinstance(result, str) and result.startswith(tools.TASK_COMPLETE_SIGNAL):
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
                        "content": "调用工具已完成" if isinstance(result, str) and 
                        result.startswith(tools.TASK_COMPLETE_SIGNAL) else result
                    })
            else:
                content = message.get("content", "")
                print(f"🤖 Agent（调用LLM结果）: {content[:200]}...")
                if content == "":
                    print(f"\nLLM结果为空。原始响应是:{response}")
                # print(f"🤖 Agent: {content[:200]}...")
                self.messages.append(message)
            
            # 保存Agent轮次执行结果
            filename = re.sub(r'[^\w\s-]', '', query).strip()[:10] or 'unnamed'
            os.makedirs(f"{self.save_dir}/planning_log", exist_ok=True)
            with open(f"{self.save_dir}/planning_log/{filename}_{turn}.json", "w") as f:
                f.write(json.dumps(self.messages, indent=True, ensure_ascii=False))
        return "达到最大轮次限制"
    
    def _execute_tool(self, tool_call: dict) -> str:
        """执行工具调用"""
        func_name = tool_call["function"]["name"]
        args_str = tool_call["function"]["arguments"]
        
        try:
            args = json.loads(args_str)
            print(f"   → 开始调用{func_name}方法, 参数:{args_str[:150]}")
        except json.JSONDecodeError:
            return f"参数解析失败: {args_str}"
        
        # print(f"🔧 {func_name}({json.dumps(args, ensure_ascii=False)[:100]}...)")
        
        if func_name in self.TOOL_FUNCTIONS:
            try:
                result = self.TOOL_FUNCTIONS[func_name](**args)
                # 确保返回的是字符串
                if isinstance(result, str):
                    display = result[:200] + "..." if len(result) > 200 else result
                else:
                    result = str(result)
                    display = result[:200] + "..." if len(result) > 200 else result
                print(f"   → 调用{func_name}方法结果:\n{display}")
                return result
            except Exception as e:
                return f"{func_name} 执行错误: {str(e)}"
        
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
    #project_dir = "/home/data/icode/baidu/miaobi/multi_agent/agents/planning"
    project_dir = "/home/data/zhonglong/icode/baidu/miaobi/multi_agent/agents/planning"
    save_name = 'test'
    #save_dir = f"/home/data/icode/baidu/miaobi/multi_agent/outputs/{save_name}"
    save_dir = f"/home/data/zhonglong/icode/baidu/miaobi/multi_agent/outputs/{save_name}"
    os.makedirs(save_dir, exist_ok=True)

    # 1. 初始化 Agent
    # 注意：确保你的 api.py 已经配置好了 API Key
    agent = PlanningAgent(
        model="deepseek-v3.2",
        audience="大众",
        language="中文",
        save_dir=save_dir

    )

    # 2. 准备输入数据
#     user_query = "ysl夜皇后和sk2神仙水哪个好"
#     brief = """
# 品牌背景：欧莱雅集团旗下高端奢侈品牌 YSL（圣罗兰），其明星单品 YSL夜皇后精华（第二代）于 2023 年完成重磅升级。作为高端夜间修护市场的领军者，该产品凭借“熬夜护肤”的核心概
# 念，在社交媒体（如小红书、微博）拥有极高的讨论度与品牌溢价，是都市职场女性及熬夜人群的首选高端精华之一。

# 产品信息：
# - 产品名称：YSL夜皇后精华（全称：YSL圣罗兰夜皇后精华）
# - 产品类别：高端夜间修护精华 / 功能性护肤品
# - 市场定位：高端奢华、高效急救、科学焕肤的夜间专属护理
# - 目标用户：核心受众为 25-40 岁左右的都市人群。具体包括：频繁加班的职场人士（都市夜归人）、追剧游戏的熬夜爱好者、跨时区出差的商务人士、睡眠不规律的新手妈妈，以及追求专业、高效、具有仪式感护肤体验的进阶消费者。

# 产品卖点：
# - 双通路机制与黄金配比：由于采用 3.4% 精密配比复合酸（甘醇酸+柠檬酸+乳酸）与 20 倍浓缩仙人掌花精萃，因此能够实现“温和焕肤”与“高效抗氧”的双重功效，抗氧化能力高达维 C 的 10 倍，为用户提供科学且立竿见影的肤质改善。
# - 卓越的修护实证数据：由于产品经过临床验证，连续使用 28 天后夜间修护效率提升 217%，且 7 天可见光泽改善、14 天淡化细纹，因此能够有效解决熬夜带来的皮肤暗沉与粗糙，极大降低了用户对于“熬夜毁脸”焦虑。
# - 水油双相创新质地与环保设计：由于采用模拟天然皮脂膜的水油分离质地，并配合可替换内胆设计，因此产品既能确保清爽不黏腻的高级使用感，又兼顾了高端消费者的环保理念与可持续消费诉求。

# 硬性要求：
# - 必须包含的关键词：['YSL夜皇后精华', 'YSL圣罗兰夜皇后精华']
# - 禁止出现的文本/词语：[]
# - 特定活动/时间点：null
#    """.strip()

#     user_input = {
#         "query": user_query,
#         "brief": brief
#     }
    
    # 笔记信息图
    user_input = {
        "query": "手机卡顿是什么原因",
        "content": """
        手机用久了变卡顿？别急着换新机！先搞清楚这四大元凶

你的手机是否也曾这样：打开APP要等半天，刷视频卡成PPT，切换应用慢如蜗牛？很多人一卡顿就觉得手机该退休了，但其实80%的卡顿问题都能自己解决。今天我们就来彻底拆解手机变慢的背后真相，让你对症下药，轻松找回流畅。

**第一大元凶：内存与存储的“角色混淆”**
很多人误以为手机卡顿是存储空间（ROM）不足，其实真正的“卡顿杀手”是运行内存（RAM）。运行内存就像手机的“临时工作台”，负责正在运行的程序。当你同时打开微信、抖音、游戏等多个应用，工作台被占满，新任务就无处安身，导致闪退、掉帧。而存储空间是你的“大仓库”，装的是照片、视频、APP等长期数据。仓库快满了虽然也会拖慢读写速度，但日常卡顿更多源于内存告急。

**解决方案**：及时关闭不用的后台应用（安卓上滑多任务界面清理，iOS上滑关闭），并定期清理APP缓存（如在微信设置-通用-存储空间中清理），能为内存快速减负。

**第二大元凶：电池老化的“隐形降频”**
如果你的手机存储空间充足，清理后依然卡顿，很可能是电池在“捣鬼”。手机电池使用2-3年后，健康度往往会低于80%（可在设置中查看）。老化的电池内阻增大，供电不稳，系统为防止意外关机，会主动启动“降频保护”——限制处理器性能。这就好比让百米运动员放慢脚步，手机自然变慢。这正是当年iPhone“降频门”背后的原理，如今安卓手机也普遍采用了类似机制。

**解决方案**：检查电池健康度，若已低于80%，更换一块原装电池（官方费用通常在100-300元）往往是性价比最高的选择，能让性能立竿见影地恢复。

**第三大元凶：系统与软件的“负担过重”**
*   **后台偷跑与恶意软件**：许多应用即使关闭也在后台偷偷运行，占用内存；来路不明的APP可能携带恶意插件，持续消耗资源。
*   **系统更新不适配**：新系统可能为老款机型带来过重负担，导致越更新越卡。
*   **存储空间过满**：当存储占用超过90%，手机读写数据会变得异常缓慢，如同塞满的抽屉找东西困难。

**解决方案**：从官方应用商店下载APP；关闭非必要应用的自启动权限；老款机型谨慎升级最新系统；定期卸载不用APP、删除大文件（如旧视频），确保存储空间剩余至少15%。

**第四大元凶：硬件性能的“自然衰老”**
处理器、闪存等硬件随着时间推移性能会自然衰减，长期高温使用也会加速老化。当硬件性能已无法满足如今越发臃肿的APP和系统需求时，卡顿便难以避免。

**长期保养习惯，让手机持久流畅**
1.  **每日随手清理**：睡前花10秒清理后台应用。
2.  **预留存储空间**：养成习惯，别把存储塞到临界点。
3.  **善待电池**：避免边充边玩，尽量让电量保持在20%-80%之间，延缓电池老化。

总之，手机卡顿是一个系统性问题。下次再遇到卡顿，不妨先从清理内存和后台开始，检查存储和电池健康，多数情况下你的手机都能“重获新生”。只有硬件确实老旧到无法满足需求时，才是考虑换机的最佳时机。
""".strip()
    }
    

    # 3. 运行 Agent
    print("--- 任务开始 ---")
    final_summary = agent.run(
        query="手机卡顿是什么原因",
        user_input=user_input,
        task_type="笔记大纲"
    )
    
    print("\n--- 最终执行结果 ---")
    print(final_summary)