# -*- coding: UTF-8 -*-
################################################################################
#
# Copyright (c) 2026 Baidu.com, Inc. All Rights Reserved
#
################################################################################
"""
本文件实现了一个商单图文的生成。

Authors: xufang07
"""

import json
import os
import re
from pathlib import Path
import inspect
from datetime import datetime
from utils.api import request_llm_v2
from agents.retrieval.process import DeepCollectAgent
from agents.planning.process import PlanningAgent
from agents.figures.process import ImageAgent
from agents.creation.process import CreationAgent
from agents.understanding.process import UnderstandingAgent

def main(query, user_input, task_type, save_dir):
    """
    agents 的入口函数
    """
    plan_dir = f"{save_dir}/plan.md" 
    demand_dir = f"{save_dir}/demand.json"
    info_dir = f"{save_dir}/report.md"
    figure_dir = f"{save_dir}/figure.md"
    understanding_dir = f"{save_dir}/understanding.md" 

    # 输入理解
    if not os.path.exists(understanding_dir):
        understanding_agent = UnderstandingAgent(
            model="deepseek-v3.2",
            audience="大众",
            language="中文",
            save_dir=save_dir
        )
        understanding_agent.run(user_input, task_type)

    with open(understanding_dir, "r", encoding="utf-8") as f:
        understanding = f.read()

    # 生成规划
    if not os.path.exists(plan_dir) or not os.path.exists(demand_dir):
        print("正在生成规划...")
        plan_agent = PlanningAgent(
            model="deepseek-v3.2",
            audience="大众",
            language="中文",
            save_dir=save_dir
        )
        plan_agent.run(query, understanding, task_type)
    with open(plan_dir, "r", encoding="utf-8") as f:
        plan = f.read()

    with open(demand_dir, "r", encoding="utf-8") as f:
        demand = json.load(f)

    # 搜集信息
    if demand["需要检索"]:
        if not os.path.exists(info_dir):
            print("正在搜集信息...")
            collect_agent = DeepCollectAgent(max_rounds=20, save_dir=save_dir)
            collect_agent.run_skill(query=demand["检索query"], max_steps=72)

        with open(info_dir, 'r', encoding='utf-8') as f:
            info = f.read()

        plan += "\n [检索信息] \n" + info
    else:
        info = ""

    # 生成配图
    if demand["需要配图"]:
        if not os.path.exists(figure_dir):
            print("正在生成配图...")
            image_agent = ImageAgent(
            model="deepseek-v3.2",               
            aspect_ratio="16:9",
            save_dir=save_dir         
            )
            image_agent.run(understanding, plan, task_type)
        with open(figure_dir, 'r', encoding='utf-8') as f:
            images = f.read()
        plan += "\n [配图] \n" + images

    # 生成最终图文
    print("正在生成文章...")
    create_agent = CreationAgent(
        model="deepseek-v3.2",
        audience="大众",
        language="中文",
        save_dir=save_dir
    )                         
    create_agent.run(
    outline=plan,
    user_input=understanding,
    task_type=task_type
    )


    

if __name__ == "__main__":
    input_path = "/home/data/icode/baidu/miaobi/multi_agent/inputs/北京情侣约会大全.json"
    with open(input_path, "r") as f:
        data = json.load(f)
    query = data['query']
    user_input = f"""
    [query] 
    {query}
    [requirements]
    {data['requirements']}
    [images]
    {data['images']}
    """ 
    task_type = data['task_type']
    save_dir = f"/home/data/icode/baidu/miaobi/multi_agent/outputs/{query}_{task_type}"
    os.makedirs(save_dir, exist_ok=True)
    main(query, user_input, task_type, save_dir)