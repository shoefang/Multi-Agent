"""
自适应信息采集 Agent
根据query复杂度动态调整检索策略
"""
import json
import os
import re
from pathlib import Path
import inspect
from datetime import datetime

import agents.retrieval.tools as tools
import agents.retrieval.prompt as prompt
from utils.api import request_llm_v2
# ============================================================
# 自适应信息采集 Agent
# ============================================================
class DeepCollectAgent:
    """
    自适应信息采集 Agent
    
    核心能力：
    1. 复杂度评估（1-5级）
    2. 动态检索（横向+纵向扩展）
    3. 信息增益评估
    4. 智能停止判断
    5. 核心观点提炼
    """
    
    def __init__(self, 
                model: str = "deepseek-v3.2",
                skills_dir: str = "skills",
                schema_dir: str = "tools_schema.json",
                blacklist: str = "./configs/sensitive_blacklist.json",
                max_rounds: int = 10,
                sucai_max_length: int = 80000,
                max_tool_content_length: int = 100000,
                save_dir: str = "./out"
                ):
        BASE_DIR = Path(__file__).parent

        # 加载工具
        self.TOOL_FUNCTIONS = {
            name: func
            for name, func in inspect.getmembers(tools, inspect.isfunction)
            if func.__module__ == tools.__name__
        }
        with open(os.path.join(BASE_DIR, schema_dir), "r") as f:
            self.TOOLS_SCHEMA = json.load(f)
        
        self.save_dir = save_dir
        self.blacklist_dir = blacklist
        self.model = model
        self.skills_dir = os.path.join(BASE_DIR, skills_dir)
        self.max_rounds = max_rounds
        self.sucai_max_length = sucai_max_length
        self.max_tool_content_length = max_tool_content_length
        
        # 状态变量
        self.messages = []  # 记录所有LLM交互的完整上下文
        self.current_skill = None
        self.complexity_info = {}
        self.collected_info = []  # 存储每篇独立素材
        self.round_info_map = []  # 跟踪每篇素材所属的轮次 [{"round": 1, "query": "xxx"}, ...]
        self.search_history = []
        self.used_queries = []
        self.current_query = ""  # 当前处理的query
    
    def _record_llm_interaction(self, interaction_type: str, request_messages: list, response: dict):
        """
        记录LLM交互到messages列表

        Args:
            interaction_type: 交互类型 (complexity_eval, expand_queries, info_gain, report)
            request_messages: 发送给LLM的消息列表
            response: LLM的响应
        """
        interaction_record = {
            "type": interaction_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "request": request_messages,
            "response": {
                "content": response.get("choices", [{}])[0].get("message", {}).get("content", ""),
                "model": response.get("model", self.model),
                "usage": response.get("usage", {})
            } if response else None
        }
        self.messages.append(interaction_record)

    def _save_messages_to_file(self, query: str, round_num: int = None):
        """
        保存messages到JSON文件

        Args:
            query: 当前查询
            round_num: 轮次号，如果为None则保存最终完整版本
        """
        os.makedirs(f"{self.save_dir}/retrieval_log", exist_ok=True)

        if round_num is not None:
            # 保存每轮的messages
            filename = f"{self.save_dir}/retrieval_log/messages_round_{round_num}.json"
        else:
            # 保存最终完整版本
            filename = f"{self.save_dir}/retrieval_log/messages_full.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "query": query,
                "total_interactions": len(self.messages),
                "messages": self.messages
            }, f, ensure_ascii=False, indent=2)

        print(f"   💾 上下文已保存: {filename}")

    def _save_skill_context(self, messages: list, step_logs: list, query: str):
        """
        保存 run_skill 的完整执行上下文（覆盖写入，每步调用后用最新状态覆盖）。

        Args:
            messages: 当前完整的 OpenAI messages 列表
            step_logs: 每步 tool call 的摘要记录列表
            query: 当前查询
        """
        path = f"{self.save_dir}/retrieval_log/skill_context.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "query": query,
                "total_steps": len(step_logs),
                "step_logs": step_logs,
                "messages": messages
            }, f, ensure_ascii=False, indent=2)


    def _get_format_user_prompt(self, query, max_rounds):
        """格式化用户Prompt"""
      
        user_prompt = prompt.TEMPLATE_PROMPT.format(
            query=query,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            max_rounds=max_rounds,
            save_dir=f"{self.save_dir}/report.md"
        )
        return user_prompt
    
    def _resolve_skill_file(self, skill_name: str = None) -> str:
        """解析要使用的 SKILL.md 文件路径。"""
        if skill_name:
            skill_path = os.path.join(self.skills_dir, skill_name, "SKILL.md")
            if os.path.exists(skill_path):
                return skill_path
            raise FileNotFoundError(f"未找到指定 skill: {skill_path}")

        preferred = os.path.join(self.skills_dir, "自适应信息采集", "SKILL.md")
        if os.path.exists(preferred):
            return preferred

        if os.path.exists(self.skills_dir):
            for item in sorted(os.listdir(self.skills_dir)):
                candidate = os.path.join(self.skills_dir, item, "SKILL.md")
                if os.path.exists(candidate):
                    return candidate

        raise FileNotFoundError(f"未在 skills 目录中找到 SKILL.md: {self.skills_dir}")

    def _serialize_tool_result(self, result) -> str:
        """将工具结果标准化为字符串，便于回填 tool message。"""
        if isinstance(result, str):
            return result

        try:
            return json.dumps(result, ensure_ascii=False)
        except Exception:
            return str(result)

    def _evaluate_query_complexity(self, query: str) -> dict:
        """
        评估query复杂度
        返回：{
            "complexity_level": 1-5,
            "dimensions": [...],
            "estimated_rounds": int,
            "max_rounds_suggestion": int
        }
        """
        print(f"\n📊 正在评估query复杂度...")

        eval_prompt = prompt.COMPLEXITY_EVALUATION_PROMPT.format(query=query)

        # 构建request messages用于记录
        request_messages = [{"role": "user", "content": eval_prompt}]

        response = request_llm_v2(
            prompt=eval_prompt,
            model_name=self.model,
            messages=None,
            tools=None
        )

        # 记录LLM交互
        self._record_llm_interaction("complexity_eval", request_messages, response)

        if not response or "choices" not in response:
            print("⚠️ 复杂度评估失败，使用默认值")
            return {
                "complexity_level": 3,
                "dimensions": ["信息收集"],
                "estimated_rounds": 3,
                "max_rounds_suggestion": 5
            }
        
        content = response["choices"][0]["message"]["content"]
        
        # 解析JSON
        try:
            # 尝试提取JSON块
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.S)
            if json_match:
                content = json_match.group(1)
            
            result = json.loads(content)
            print(f"✅ 复杂度评估完成: {result['complexity_level']}级")
            print(f"   核心维度: {', '.join(result.get('dimensions', []))}")
            print(f"   预估轮次: {result.get('estimated_rounds', 3)}轮")
            return result
        except Exception as e:
            print(f"⚠️ 解析复杂度评估结果失败: {e}")
            return {
                "complexity_level": 3,
                "dimensions": ["信息收集"],
                "estimated_rounds": 3,
                "max_rounds_suggestion": 5
            }
    
    def _resolve_max_rounds(self, runtime_max_rounds: int, complexity_info: dict) -> int:
        """
        根据query复杂度动态确定最大检索轮次。

        runtime_max_rounds: 运行时可接受的上限（来自run参数或实例默认值）
        complexity_info: 复杂度评估结果
        """
        suggestion = complexity_info.get("max_rounds_suggestion")
        estimated = complexity_info.get("estimated_rounds")

        # 优先使用LLM返回的建议值，若缺失则回退到估计轮次+1
        dynamic_rounds = suggestion + 2 if isinstance(suggestion, int) else None
        if dynamic_rounds is None and isinstance(estimated, int):
            dynamic_rounds = estimated + 3

        # 最终兜底
        if dynamic_rounds is None:
            dynamic_rounds = runtime_max_rounds

        # 约束在合理区间，且不超过运行时上限
        dynamic_rounds = max(1, dynamic_rounds)
        return min(runtime_max_rounds, dynamic_rounds)

    def _generate_expanded_queries(self, query: str, current_round: int, expansion_direction: str = "auto") -> dict:
        """
        生成本轮的扩展检索词
        expansion_direction: "horizontal" | "vertical" | "auto"
        """
        # 构建已收集信息的摘要（按轮次分组）
        if self.collected_info and self.round_info_map:
            # 按轮次分组素材
            round_groups = {}
            for i, info in enumerate(self.collected_info):
                if i < len(self.round_info_map):
                    round_num = self.round_info_map[i]["round"]
                    if round_num not in round_groups:
                        round_groups[round_num] = []
                    round_groups[round_num].append(info)

            # 生成摘要
            info_parts = []
            for round_num in sorted(round_groups.keys())[-3:]:  # 只取最近3轮
                round_content = "\n".join(round_groups[round_num])
                info_parts.append(f"- 第{round_num}轮: {round_content[:200]}...")
            info_summary = "\n".join(info_parts)
        else:
            info_summary = "暂无已收集信息"

        gen_prompt = prompt.EXPAND_QUERIES_PROMPT.format(
            query=query,
            current_round=current_round,
            collected_info_summary=info_summary,
            used_queries=", ".join(self.used_queries) if self.used_queries else "暂无",
            expansion_direction=expansion_direction
        )

        # 构建request messages用于记录
        request_messages = [{"role": "user", "content": gen_prompt}]

        response = request_llm_v2(
            prompt=gen_prompt,
            model_name=self.model,
            messages=None,
            tools=None
        )

        # 记录LLM交互
        self._record_llm_interaction("expand_queries", request_messages, response)

        if not response or "choices" not in response:
            print("⚠️ 生成检索词失败，使用原始query")
            return {
                "round_number": current_round,
                "expansion_type": "vertical",
                "queries": [query],
                "focus": "基础信息收集",
                "reasoning": "生成失败，回退到原始query"
            }
        
        content = response["choices"][0]["message"]["content"]
        
        try:
            # 尝试提取JSON块
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.S)
            if json_match:
                content = json_match.group(1)
            
            result = json.loads(content)
            print(f"✅ 生成检索词: {result['expansion_type']}扩展")
            print(f"   检索词: {', '.join(result['queries'])}")
            return result
        except Exception as e:
            print(f"⚠️ 解析检索词失败: {e}")
            return {
                "round_number": current_round,
                "expansion_type": "vertical",
                "queries": [query],
                "focus": "基础信息收集",
                "reasoning": "解析失败，回退到原始query"
            }
    
    def _evaluate_info_gain(self, previous_info: str, new_info: str, core_dimensions: list) -> dict:
        """
        评估信息增益
        返回：{
            "new_info_score": 0.0-1.0,
            "covered_dimensions": [...],
            "missing_dimensions": [...],
            "continue_search": bool
        }
        """
        eval_prompt = prompt.INFO_GAIN_EVALUATION_PROMPT.format(
            previous_info=previous_info or "这是第一轮检索",
            new_info=new_info,
            core_dimensions=", ".join(core_dimensions)
        )

        # 构建request messages用于记录
        request_messages = [{"role": "user", "content": eval_prompt}]

        response = request_llm_v2(
            prompt=eval_prompt,
            model_name=self.model,
            messages=None,
            tools=None
        )

        # 记录LLM交互
        self._record_llm_interaction("info_gain", request_messages, response)

        if not response or "choices" not in response:
            print("⚠️ 信息增益评估失败")
            return {
                "new_info_score": 0.5,
                "covered_dimensions": [],
                "missing_dimensions": core_dimensions,
                "continue_search": True
            }
        
        content = response["choices"][0]["message"]["content"]
        
        try:
            # 尝试提取JSON块
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.S)
            if json_match:
                content = json_match.group(1)
            
            result = json.loads(content)
            print(f"📈 信息增益评分: {result['new_info_score']:.2f}")
            print(f"   已覆盖维度: {', '.join(result.get('covered_dimensions', []))}")
            if result.get('missing_dimensions'):
                print(f"   缺失维度: {', '.join(result['missing_dimensions'])}")
            return result
        except Exception as e:
            print(f"⚠️ 解析信息增益评估失败: {e}")
            return {
                "new_info_score": 0.5,
                "covered_dimensions": [],
                "missing_dimensions": core_dimensions,
                "continue_search": True
            }
    
    def _calculate_total_length(self) -> int:
        """
        计算所有已收集素材的总长度（字符数）
        """
        return sum(len(info) for info in self.collected_info)

    def _should_stop_search(self, current_round: int, max_rounds: int) -> tuple:
        """
        判断是否应该停止检索
        返回: (should_stop: bool, reason: str)
        """

        # 条件1: 达到最大轮次
        if current_round >= max_rounds:
            return True, "达到最大轮次限制"

        # 条件2: 素材总长度超过限制
        total_length = self._calculate_total_length()
        if total_length > self.sucai_max_length:
            return True, f"素材总长度超过限制 ({total_length} > {self.sucai_max_length})"

        # 条件3: 连续2轮低增益
        if len(self.search_history) >= 2:
            last_two_scores = [
                h.get("new_info_score", 1.0)
                for h in self.search_history[-2:]
            ]
            if all(score <= 0.4 for score in last_two_scores):
                return True, "连续2轮信息增益过低"

        # 条件4: 维度全覆盖且增益下降
        if self.search_history:
            last_eval = self.search_history[-1]
            if (not last_eval.get("missing_dimensions") and
                last_eval.get("new_info_score", 1.0) < 0.5):
                return True, "所有维度已覆盖且信息增益下降"


        return False, ""
    
    def _generate_report(self, query: str, all_info: list, round_info_map: list, complexity_info: dict, actual_rounds: int, max_rounds: int) -> str:
        """生成最终报告"""
        print("\n📄 正在生成报告...")

        # 按轮次分组合并所有信息
        round_groups = {}
        for i, info in enumerate(all_info):
            if i < len(round_info_map):
                round_num = round_info_map[i]["round"]
                if round_num not in round_groups:
                    round_groups[round_num] = []
                round_groups[round_num].append(info)
            else:
                # 兼容旧数据格式
                round_groups[i + 1] = [info]

        # 生成按轮次组织的内容
        all_collected = "\n\n".join([
            f"=== 第{round_num}轮检索结果 ===\n" + "\n\n".join(round_groups[round_num])
            for round_num in sorted(round_groups.keys())
        ])

        complexity_level = complexity_info.get("complexity_level", 3)
        output_requirements = prompt.get_report_requirements_by_complexity(complexity_level)

        report_prompt = prompt.REPORT_GENERATION_PROMPT.format(
            query=query,
            complexity_level=complexity_level,
            actual_rounds=actual_rounds,
            max_rounds=max_rounds,
            all_collected_info=all_collected[:self.sucai_max_length],
            output_requirements=output_requirements
        )

        # 构建request messages用于记录
        request_messages = [{"role": "user", "content": report_prompt}]

        response = request_llm_v2(
            prompt=report_prompt,
            model_name=self.model,
            messages=None,
            tools=None
        )

        # 记录LLM交互
        self._record_llm_interaction("report_generation", request_messages, response)

        if not response or "choices" not in response:
            return "# 报告生成失败\n\n未能生成有效报告，请检查日志。"

        report = response["choices"][0]["message"]["content"]
        
        # 保存报告
        report_path = f"{self.save_dir}/report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"✅ 报告已保存到: {report_path}")
        return report
    
    def run(self, query: str, max_rounds: int = None) -> str:
        """
        执行自适应信息采集

        Args:
            query: 用户查询
            max_rounds: 运行时轮次上限（实际值会按复杂度动态收敛）

        Returns:
            最终报告内容
        """
        runtime_max_rounds = max_rounds if max_rounds is not None else self.max_rounds

        # 重置状态变量
        self.messages = []  # 清空上下文记录
        self.current_query = query
        self.collected_info = []
        self.round_info_map = []  # 跟踪每篇素材所属的轮次
        self.search_history = []
        self.used_queries = []

        print(f"\n🚀 收到请求: {query}")
        print(f"⚙️ 运行时轮次上限: {runtime_max_rounds}")

        # ========================================
        # Phase 1: 复杂度评估
        # ========================================
        self.complexity_info = self._evaluate_query_complexity(query)
        complexity_level = self.complexity_info.get("complexity_level", 3)
        core_dimensions = self.complexity_info.get("dimensions", ["信息收集"])
        max_rounds = self._resolve_max_rounds(runtime_max_rounds, self.complexity_info)

        _ = self._get_format_user_prompt(query, max_rounds)
        print(f"🎯 动态最大检索轮次: {max_rounds}")

        # 保存复杂度评估后的上下文
        self._save_messages_to_file(query, 0)
        
        # 根据复杂度调整display和undisplay参数
        if complexity_level <= 2:
            display_count, undisplay_count = 1, 2
        elif complexity_level <= 4:
            display_count, undisplay_count = 1, 3
        else:
            display_count, undisplay_count = 1, 4
        
        # ========================================
        # Phase 2: 动态检索循环
        # ========================================
        current_round = 0
        self.collected_info = []
        self.round_info_map = []  # 跟踪每篇素材所属的轮次
        self.search_history = []
        self.used_queries = []
        
        while current_round < max_rounds:
            current_round += 1
            print(f"\n{'='*60}")
            print(f"🔄 第 {current_round}/{max_rounds} 轮检索")
            print(f"{'='*60}")
            
            # Step 1: 生成检索词
            if current_round == 1:
                # 第一轮：使用原始query
                search_plan = {
                    "round_number": 1,
                    "expansion_type": "vertical",
                    "queries": [query],
                    "focus": "基础信息收集"
                }
            else:
                # 后续轮次：动态生成扩展检索词
                expansion_dir = "horizontal" if current_round % 2 == 0 else "vertical"
                search_plan = self._generate_expanded_queries(
                    query, current_round, expansion_dir
                )
            
            # Step 2: 执行检索
            round_results = []
            for search_query in search_plan["queries"]:
                if search_query in self.used_queries:
                    print(f"   ⏭️ 跳过重复检索词: {search_query}")
                    continue

                self.used_queries.append(search_query)
                print(f"   🔍 检索: {search_query}")

                # 调用search_docs_list工具，获取素材列表
                if "search_docs" in self.TOOL_FUNCTIONS:
                    result_list = self.TOOL_FUNCTIONS["search_docs"](
                        query=search_query,
                        display=display_count,
                        undisplay=undisplay_count
                    )
                    # 将每篇素材独立添加到 collected_info
                    for doc_content in result_list:
                        self.collected_info.append(doc_content)
                        self.round_info_map.append({
                            "round": current_round,
                            "query": search_query
                        })
                    round_results.extend(result_list)
                else:
                    print("   ⚠️ search_docs_list工具不可用")

            # 如果本轮没有获取到任何素材，跳过后续步骤
            if not round_results:
                print(f"   ⚠️ 本轮未获取到任何素材")
                continue

            # 合并本轮结果用于信息增益评估
            round_info = "\n\n".join(round_results)
            
            # Step 3: 信息增益评估
            # 获取上一轮的素材用于对比
            previous_round_docs = []
            if current_round > 1:
                for i, meta in enumerate(self.round_info_map):
                    if meta["round"] == current_round - 1 and i < len(self.collected_info):
                        previous_round_docs.append(self.collected_info[i])
            previous_info = "\n\n".join(previous_round_docs) if previous_round_docs else ""

            gain_eval = self._evaluate_info_gain(
                previous_info, round_info, core_dimensions
            )
            self.search_history.append(gain_eval)
            
            # 保存本轮日志
            os.makedirs(f"{self.save_dir}/retrieval_log", exist_ok=True)
            log_data = {
                "round": current_round,
                "search_plan": search_plan,
                "gain_evaluation": gain_eval,
                "used_queries": self.used_queries
            }
            with open(f"{self.save_dir}/retrieval_log/{current_round}.json", "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            # 保存本轮的LLM上下文
            self._save_messages_to_file(query, current_round)
            
            # Step 4: 判断是否停止
            should_stop, stop_reason = self._should_stop_search(current_round, max_rounds)
            if should_stop:
                # 如果是因为素材超限，逐篇舍弃直到满足长度限制
                if "素材总长度超过限制" in stop_reason:
                    total_discarded = 0
                    discarded_count = 0
                    while self._calculate_total_length() > self.sucai_max_length and self.collected_info:
                        discarded_info = self.collected_info.pop()
                        self.round_info_map.pop()  # 同步移除元数据
                        discarded_length = len(discarded_info)
                        total_discarded += discarded_length
                        discarded_count += 1
                    print(f"\n⚠️ 素材超限，舍弃了 {discarded_count} 篇素材（总长度: {total_discarded} 字符）")
                print(f"\n🛑 停止检索: {stop_reason}")
                break
        
        # ========================================
        # Phase 3: 报告生成
        # ========================================
        report = self._generate_report(
            query,
            self.collected_info,
            self.round_info_map,
            self.complexity_info,
            current_round,
            max_rounds
        )

        # 保存完整的LLM上下文（包含所有交互记录）
        self._save_messages_to_file(query)

        print(f"\n✅ 任务完成！")
        print(f"📊 实际检索轮次: {current_round}/{max_rounds}")
        print(f"📁 报告路径: {self.save_dir}")
        print(f"💾 完整上下文: {self.save_dir}/retrieval_log/messages_full.json")

        return report
    
    def run_skill(self, query: str, max_steps: int = 24, skill_name: str = None) -> str:
        """
        基于 SKILL + tools_schema 的通用 Tool Calling 执行模式。

        Args:
            query: 用户查询
            max_steps: 最大交互步数，避免循环失控
            skill_name: 指定 skill 目录名（可选）

        Returns:
            最终摘要或模型返回内容
        """
        self.current_query = query
        step_logs = []

        skill_path = self._resolve_skill_file(skill_name)
        system_prompt = Path(skill_path).read_text(encoding="utf-8")
        user_prompt = self._get_format_user_prompt(query, self.max_rounds)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        print(f"\n🚀 [SKILL模式] 收到请求: {query}")
        print(f"📘 使用Skill: {skill_path}")

        for step in range(1, max_steps + 1):
            print(f"\n🤖 [SKILL模式] Step {step}/{max_steps}")

            response = request_llm_v2(
                prompt=None,
                model_name=self.model,
                messages=messages,
                tools=self.TOOLS_SCHEMA
            )

            if not response or "choices" not in response or not response["choices"]:
                return "Skill执行失败：LLM无有效返回"

            message = response["choices"][0].get("message", {})
            tool_calls = message.get("tool_calls") or []

            assistant_message = {
                "role": "assistant",
                "content": message.get("content", "")
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)

            if not tool_calls:
                content = message.get("content", "")
                if isinstance(content, str) and content.startswith(tools.TASK_COMPLETE_SIGNAL):
                    payload_str = content[len(tools.TASK_COMPLETE_SIGNAL):]
                    try:
                        payload = json.loads(payload_str) if payload_str else {}
                    except Exception:
                        payload = {}
                    self._save_skill_context(messages, step_logs, query)
                    return payload.get("summary", "任务完成")
                # 模型未调用工具也未触发完成信号，记录诊断信息
                print(f"\n⚠️ [WARN] Step {step}: 模型未返回 tool_call，直接输出文本内容")
                print(f"   内容预览: {(content or '(空)')[:300]}")
                print(f"   当前消息轮次: {len(messages)}")
                # 将诊断上下文保存到文件
                debug_path = f"{self.save_dir}/retrieval_log/debug_step{step}.json"
                os.makedirs(os.path.dirname(debug_path), exist_ok=True)
                with open(debug_path, "w", encoding="utf-8") as _f:
                    json.dump({"step": step, "model_content": content, "messages": messages}, _f, ensure_ascii=False, indent=2)
                print(f"   诊断上下文已保存: {debug_path}")
                self._save_skill_context(messages, step_logs, query)
                return content or "Skill执行结束，但未返回最终内容"

            for tool_call in tool_calls:
                tool_result = self._execute_tool(
                    tool_call,
                    parent_query=query
                )
                tool_content = self._serialize_tool_result(tool_result)

                if len(tool_content) > self.max_tool_content_length:
                    tool_content = tool_content[:self.max_tool_content_length] + "\n...[内容已截断]"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": tool_content
                })

                # 记录本次 tool call 摘要并覆盖保存完整上下文
                func_name = tool_call.get("function", {}).get("name", "")
                try:
                    args_obj = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                    args_preview = json.dumps(args_obj, ensure_ascii=False)[:200]
                except Exception:
                    args_preview = str(tool_call.get("function", {}).get("arguments", ""))[:200]
                step_logs.append({
                    "step": step,
                    "tool": func_name,
                    "args_preview": args_preview,
                    "result_preview": tool_content[:300],
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                self._save_skill_context(messages, step_logs, query)

                if tool_content.startswith(tools.TASK_COMPLETE_SIGNAL):
                    payload_str = tool_content[len(tools.TASK_COMPLETE_SIGNAL):]
                    try:
                        payload = json.loads(payload_str) if payload_str else {}
                    except Exception:
                        payload = {}

                    files_created = payload.get("files_created", [])
                    if files_created:
                        print(f"📁 生成文件: {files_created}")
                    return payload.get("summary", "任务完成")

        self._save_skill_context(messages, step_logs, query)
        return f"Skill执行超出最大步数({max_steps})，请检查提示词或工具链路"

    def _execute_tool(self, tool_call: dict, parent_query: str = "") -> str:
        """执行工具调用，并对 run_sub_skill 注入父任务 query。"""
        func_name = tool_call["function"]["name"]
        args_str = tool_call["function"].get("arguments", "{}")

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return f"参数解析失败: {args_str}"

        # 子 skill 继承主 run_skill 的 query；步数预算由子 skill 自身策略决定
        if func_name == "run_sub_skill":
            if parent_query:
                args["query"] = parent_query
            tool_call["function"]["arguments"] = json.dumps(args, ensure_ascii=False)

        print(f"🔧 {func_name}({json.dumps(args, ensure_ascii=False)[:100]}...)")

        if func_name in self.TOOL_FUNCTIONS:
            try:
                result = self.TOOL_FUNCTIONS[func_name](**args)
                if isinstance(result, str):
                    display = result[:200] + "..." if len(result) > 200 else result
                else:
                    result_text = self._serialize_tool_result(result)
                    display = result_text[:200] + "..." if len(result_text) > 200 else result_text
                print(f"   → {display}")
                return result
            except Exception as e:
                return f"执行错误: {str(e)}"

        return f"未知工具: {func_name}"


# ============================================================
# 使用示例
# ============================================================
if __name__ == "__main__":
    # 测试query
    query = "北京元宵节去哪玩" # "大模型时代Agent的发展" # "飞科和飞利浦剃须刀哪个好"

    # 创建Agent（可自定义最大轮次）
    agent = DeepCollectAgent(max_rounds=20)
    
    # 执行（也可在run时指定max_rounds）
    for query in ["手机卡顿原因", "公孙穴深度解析", "为啥先逛洛阳再去开封"]:
        # report = agent.run(query=query)
        report = agent.run_skill(query=query, max_steps=36)
        
        print("\n" + "=" * 60)
        print("📄 报告预览（前300字）:")
        print("=" * 60)
        print(report[:500])
        print("\n...")
        # ipdb.set_trace()