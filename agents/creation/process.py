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
    save_name = "test_0330_10"
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

    # 2. 准备输入数据
#     outline = """
# # 十年数码博主跨界护肤：YSL夜皇后和SK2神仙水，我为什么选了前者？

# ## 开头

# 做了十年数码测评，习惯了拆解芯片参数、对比屏幕素质、测试续航表现。最近朋友问我护肤品，特别是YSL夜皇后精华和SK2神仙水哪个好，我下意识地用上了那套分析框架。

# 数码和护肤看似不搭边，但底层逻辑相通：都是技术产品，都有目标用户，都需要在特定场景下发挥作用。

# ## 分析框架：把护肤品当电子产品看

# 数码产品评测有几个核心维度：性能、适用场景、长期体验、性价比。护肤品其实也一样。

# 性能对应的是效果，适用场景对应的是肤质和作息，长期体验对应的是使用感和稳定性，性价比就不必多说了。

# ## 性能分析：夜间修复 vs 日常维稳

# SK2神仙水更像是一台日常办公本，稳定、均衡、适合长期使用。它的核心是Pitera，主打的是皮肤状态的平衡和维稳。

# YSL夜皇后精华则像是一台高性能游戏本，针对特定场景做了优化。它的设计思路很明确：为熬夜人群提供高效的夜间修复。3.4%复合酸负责温和焕肤，仙人掌花精萃负责抗氧化，这个组合在夜间修复这个细分领域确实有针对性。

# ## 适用场景：你的生活作息决定选择

# 如果你作息规律，皮肤状态稳定，只是需要日常维护，神仙水这种均衡型产品可能更合适。

# 但如果你是典型的都市夜归人——加班、追剧、跨时区出差，睡眠不规律是常态，那YSL夜皇后精华的设计就更有针对性。它的水油分离质地模拟皮脂膜，使用感清爽不黏腻，这点对熬夜后皮肤状态不佳的人来说很重要。

# ## 长期体验：使用细节观察

# 用了几个月，有几个细节值得分享：

# 1. 替换装设计很实用，减少了包装浪费，这点在数码圈叫可持续设计
# 2. 质地确实清爽，吸收快，不会影响后续睡眠
# 3. 连续使用一段时间后，早晨的皮肤状态确实更稳定，暗沉改善明显

# ## 技术路线差异

# 从技术角度看，两款产品走了不同的路线：

# 神仙水是单一核心成分的深度优化，追求的是长期稳定的效果。

# YSL夜皇后精华是多成分协同作战，针对的是夜间修复这个具体场景。它的临床数据——28天修护效率提升217%——在数码圈相当于跑分成绩，是量化效果的参考。

# ## 个人选择逻辑

# 我选了YSL夜皇后精华，不是因为神仙水不好，而是因为我的使用场景更匹配。

# 数码评测教会我一件事：没有完美的产品，只有最适合的产品。YSL夜皇后精华在夜间修复这个细分场景做了针对性优化，而我的作息恰好需要这种针对性。

# ## 给读者的建议

# 别问哪个更好，先问自己几个问题：

# 1. 你的主要护肤需求是什么？
# 2. 你的生活作息是怎样的？
# 3. 你更看重即时效果还是长期稳定？

# 想清楚这些，选择就简单了。YSL夜皇后精华适合那些需要高效夜间修复的人，神仙水适合追求长期皮肤平衡的人。

# 两款都是好产品，只是服务的人群不同。
# """.strip()
#     images = {
#   "images": {
#     "image_1": {
#       "url": "https://example.com/cover_tech_skincare.jpg",
#       "description": "一张极简的数码桌面，背景是一个机械键盘和一台微单相机，前方并排摆放着YSL夜皇后精华和SK2神仙水。光影错落，呈现出科技评测的冷调质感。",
#       "caption": "当数码博主的桌面多了两瓶‘性能怪兽’：护肤本质上也是一场关于参数与体感的博弈。"
#     },
#     "image_2": {
#       "url": "https://example.com/texture_macro.jpg",
#       "description": "YSL夜皇后精华的近距离宏观特写，清晰展示其水油分离的双层质地（黄金水油比），气泡在光影下像精密的化学元件。",
#       "caption": "近距离观察夜皇后的‘双层架构’：3.4%复合酸+仙人掌花精萃，这种配比逻辑像极了高性能电脑的冗余设计。"
#     },
#     "image_3": {
#       "url": "https://example.com/night_coding_scene.jpg",
#       "description": "光线昏暗的深夜环境，一台MacBook显示器亮着（屏幕上是代码或剪辑界面），旁边摆放着一支打开盖子的YSL夜皇后精华，氛围感拉满。",
#       "caption": "凌晨两点的修护实测：在高强度‘运行’之后，给皮肤进行一次及时的‘底层系统优化’。"
#     },
#     "image_4": {
#       "url": "https://example.com/final_comparison.jpg",
#       "description": "两支产品摆放在一起，背景是一张画有逻辑图或跑分雷达图的白纸，焦点落在YSL夜皇后精华上。",
#       "caption": "没有完美的‘硬件’，只有最匹配的‘方案’。在熬夜这个特定场景下，我把这一票投给夜皇后。"
#     }
#   }
# }



#     outline = """
#     {
#   "标题": "手机卡顿别急着换！四大元凶揭秘",
#   "第一页": {
#     "内容": "大字标题：手机卡顿别急着换！四大元凶揭秘\n副标题：80%的卡顿都能自己解决\n视觉元素：手机卡顿表情包 + 流畅手机对比图\n核心文案：你的手机是否也曾这样？打开APP等半天，刷视频卡成PPT",
#     "传达核心": "制造悬念，直击用户手机卡顿痛点，引发共鸣"
#   },
#   "第二页": {
#     "内容": "标题：元凶一：内存与存储的『角色混淆』\n视觉元素：内存RAM vs 存储ROM对比图\n核心文案：• 运行内存（RAM）= 临时工作台\n• 存储空间（ROM）= 大仓库\n• 卡顿真凶：RAM被占满\n解决方案：及时清理后台应用",
#     "传达核心": "澄清常见误区，解释内存与存储的区别"
#   },
#   "第三页": {
#     "内容": "标题：元凶二：电池老化的『隐形降频』\n视觉元素：电池健康度示意图 + 降频保护机制图\n核心文案：• 电池健康度＜80% → 启动降频保护\n• 系统限制处理器性能\n• 防止意外关机\n解决方案：检查电池健康度，更换原装电池",
#     "传达核心": "揭示电池老化导致的性能下降机制"
#   },
#   "第四页": {
#     "内容": "标题：元凶三&四：系统负担 + 硬件衰老\n视觉元素：APP后台偷跑示意图 + 硬件老化时间线\n核心文案：• 后台偷跑APP占用资源\n• 恶意软件持续消耗\n• 系统更新不适配老机型\n• 硬件性能自然衰减\n解决方案：关闭自启动权限 + 谨慎升级系统",
#     "传达核心": "展示软件和硬件层面的卡顿原因"
#   },
#   "第五页": {
#     "内容": "标题：长期保养习惯，让手机持久流畅\n视觉元素：每日保养清单视觉图\n核心文案：• 每日随手清理后台\n• 预留15%存储空间\n• 电量保持在20%-80%\n• 避免边充边玩\n结尾金句：对症下药，手机重获新生",
#     "传达核心": "提供实用保养建议，强化行动号召"
#   }
# }
# """
#     images = []

    user_input = {
        "user_demand": """【摩天档案】投资50亿 苏北第一高楼 326.6米淮安雨润中央新天地能否涅槃重生？ 江苏高楼迷  供稿 https://mmbiz.qpic.cn/mmbiz_png/JlJfhcfYiadAPjnwzTzichuDhN1FdcTSULL7RIkbgdIX0rrY8EhTPIZWiaX4RLIfRrUjaTGeKBV0fiaGhtoRIVFqbw/640?wx_fmt=png&from=appmsg&watermark=1#imgIndex=0 【摩天档案】投资 50 亿苏北第一高楼 326.6 米淮安雨润中央新天地能否涅槃重生？ 淮安雨润中央新天地位于淮安市淮海广场东南角，是雨润集团与南京中商共同投资建设的城市综合体项目，总投资 50 亿元，占地面积 66 亩，总建筑面积达 52 万平方米。项目主体建筑雨润国际大厦规划高度 326.6 米，建成后将成为苏北第一高楼，也是淮安标志性城市名片。 项目定位为集星级酒店、主题百货、超市卖场、高档公寓、写字楼及配套设施于一体的现代化大型城市综合体，提供购物、办公、住宿、餐饮、娱乐、休闲、健身等 “一站式服务”。其设计由美国凯里森、UDG 上海联创等国际国内顶尖团队操刀，将商业功能与建筑艺术深度融合。 项目于 2010 年 9 月举行开工仪式，原计划五年内全部完工，主体商业部分三年内建成并投入试运营。按规划，建成后预计年销售超 20 亿元，员工总数可达 10000 人以上，将为淮安商业和第三产业发展注入强劲动力。 然而，项目推进过程波折不断，因资金问题多次陷入停滞。2018 年，因拖欠中建三局工程款约 3.2 亿元引发诉讼；2022 年 4 月，中建四局以 31.6 亿元中标负责后续建设，清江浦区政府也多次与雨润集团协商推进复工，但截至 2023 年 12 月，项目规划调整仍未完成，复工进展依旧不明朗。 雨润国际大厦最初规划高度 326.6 米，后调整为 317 米，无论最终高度如何，都将刷新苏北城市的天际线。大厦采用现代简约的玻璃幕墙设计，挺拔的楼体如同指向天空的标尺，与淮安水渡口广场的电信大楼、淮安金玺角广场等建筑形成新旧呼应的城市轮廓。 站在淮海广场眺望，雨润中央新天地的工地与周边繁华的商圈形成鲜明对比。围挡内的塔吊静立在暮色里，未完工的钢结构框架在夜风中沉默，仿佛在诉说着这座城市曾有的雄心。它曾被寄予厚望，承载着淮安向特大型中心城市迈进的梦想。 项目原址是淮安最核心的商业地段，南瞰美丽清纯的洪泽湖，北望淮安涟水机场，地理位置得天独厚。按照最初的构想，这里将成为辐射周边 2000 万人口的商业核心，让淮安的城市能级跃上新台阶。如今，这份构想仍在等待落地的契机。 多年来，淮安的地标建筑几经更迭：从水渡口广场 128 米的电信大楼，到预计 150 米的淮安金玺角广场，雨润国际大厦本应是接过 “苏北第一高楼” 桂冠的下一个主角。它的玻璃幕墙本应反射着里运河的波光，成为淮安人向外地朋友介绍家乡的骄傲。 尽管复工之路坎坷，但城市发展的脚步从未停歇。淮海广场的车流依旧川流不息，周边的商业体持续焕发生机，人们仍在期待这座摩天大楼能真正崛起。当塔吊重新转动、玻璃幕墙开始安装的那天，淮安的天际线将迎来新的高度。 它的命运，如同一场未完待续的城市叙事。每一次关于复工的消息，都牵动着淮安人的心；每一次工地的动静，都让人们重新燃起对未来的期许。这座 326.6 米的摩天大楼，不仅是建筑的高度，更是一座城市韧性与希望的象征。 无论未来何时竣工，雨润中央新天地的故事都已成为淮安城市记忆的一部分。它见证着城市发展的起伏，也承载着市民对美好生活的向往。人们始终相信，这座蛰伏多年的摩天大楼终将迎来涅槃重生的时刻，在里运河畔绽放出应有的光彩。 https://mmbiz.qpic.cn/mmbiz_jpg/JlJfhcfYiadAPjnwzTzichuDhN1FdcTSULoxiawKHozjq28dcl1tsK0xmJDOmcnE3XUpCDmaMy0WicbJ8TO4oF06qA/640?wx_fmt=jpeg&from=appmsg&watermark=1#imgIndex=1 延伸阅读： 中国地铁通车里程世界第一  断崖式领先  很多国家除了1-2个大城市别的城市就没地铁了 江苏南京地铁通往安徽滁州马鞍山 压力给到了合肥 安徽地铁第四城进度 马鞍山即将迎来地铁时代 安徽地铁第五城！黄山轨道交通t1线快速推进 一期工程预计2027年4月开通运营 2026各城市最新200米以上高楼榜单 【摩天汇总】辽宁省各地市第一高楼统计汇总 【摩天汇总】山西各地市第一高楼统计 【摩天汇总】贵州各州市第一高楼统计 【摩天汇总】四川各地第一高楼 【摩天汇总】海南省各地第一高楼 【摩天汇总】湖北各地市第一高楼统计 【摩天汇总】湖南省各地市第一高楼 【摩天汇总】四川各地第一高楼 【摩天汇总】云南省各地州市第一高楼 【摩天统计】安徽各地市第一高楼汇总 【摩天汇总】广东各地市第一高楼统计 【摩天汇总】广西各地市第一高楼 【摩天汇总】河北各城市“第一高楼”汇总 【高楼档案】山东省16地级市封顶第一高楼 【摩天汇总】河南省各地第一高楼汇总 【摩天汇总】江苏各地市第一高楼 【摩天汇总】江西各城市“第一高楼”汇总 【摩天汇总】浙江各地市第一高楼 【在建摩天】陕西第一高楼 中国国际丝路中心大厦 100层498米 【摩天地标】沙特宣布,新全球第一高楼1007米“吉达塔”将于2028年建成 【规划摩天】总投资超190亿元 98层450米！东莞“第一高楼”，华润置地中心 ‌【在建摩天】114亿！浙江杭州门面担当  目前在建的400米高楼 杭州云城北综合体主塔楼（金钥匙） 【摩天规划】刘强东给力 江苏宿迁未来可期  规划首座200米级高楼：京东未来峰项目 【摩天地标】长沙开福北 高岭最新规划，有超级城铁站 【在建摩天】75.43亿元 393.9米！原恒大总部大楼悄悄“重生”394.4米深圳湾金融中心大厦 已出地面 【摩天规划】 广东湛江79层360米地标商务中心降至250米 【摩天预测】北方第二栋500m+“中信大厦”？ 【在建摩天】投资超百亿 南京江北新区在建499.8米！"江苏第一高楼" 高度缩水天线凑 【摩天规划】香港启德机场地块，将建290米新大楼 【摩天规划】新疆克拉玛依249米“亚欧之心”降至150米 【摩天喜讯】  投资95亿！ 海南第一高楼428米海南中心核心筒正式封顶！自贸港的新动力 【海外摩天】日本天际线也要起来了 投资5000亿日元！日本第一高楼！“世界最胖的摩天高楼”390米东京火矩塔 出地面施工中 【摩天规划】湖北333米中建荆州之星 【摩天规划】云南大理市城区第一高楼为拟建的180米高的大华中心 安徽安庆的200米摩天安庆之星建设中  200+安庆之冠 双200+充满期待 【摩天规划】广州会展中区CBD，规划图有450米摩天 收紧之下最后一栋在建准500米级别摩天突破百米大关 【摩天档案】30.63亿 河北邢台第一高楼176m路桥商业大厦 安徽淮南第一高楼金融世家 【高楼档案】山东威海第一高楼  41层171m威海中信大厦 淮海之心 徐州 准300+摩天的三足鼎立时代即将到来 168米瑶海天地 合肥东部新地标 安徽阜阳城市天际线 安徽第一高摩天双塔 蚌埠城市城建高楼 堪称安徽城建第二城 107 亿 西南地区第一高楼！成都中海西南总部大厦489米95层主体结构施工 已建至57层 【摩天前瞻】从729米到499.15米 苏州中南中心 国内最深基坑、BIM全周期技术，将成长三角新地标！""",
        "outline": "",
        "images": "",
        "reference": ""
    }

    # 3. 运行 Agent
    print("--- 任务开始 ---")
    final_summary = agent.run(
        outline="",
        user_input=user_input,
        task_type="lite长图文"
    )
    
    print("\n--- 最终执行结果 ---")
    print(final_summary)


