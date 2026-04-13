#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
 Copyright (c) 2025 Baidu.com, Inc. All Rights Reserved
"""

import requests
import json
import sys
import time
import re
import traceback
from utils.deepseek_agent import DSAgent
import utils.post_process as post_process



MAX_RETRY_TIMES = 3

def request_ds_agent(prompt, system_prompt=None, model="deepseek-r1", max_tokens=4096, source_from=None):
    """
    请求ds-agent
    """
    if not prompt:
        return None
    result = None
    ds_agent = DSAgent()

    for i in range(MAX_RETRY_TIMES):
        try:
            result = ds_agent.request(user_prompt=prompt, sys_prompt=system_prompt, model=model, \
                                      max_tokens=max_tokens, source_from=source_from)
            if not result.get('reasoning_content'):
                result["reasoning_content"] = f"模型{model}没有推理过程"
            return result['content']

        except Exception as e:
            print("request failed: {}".format(e))
            time.sleep(i + 5)
            continue

    return result


def request_qianfan(prompt, system_prompt=None, model="ernie-x1-turbo-32k", max_tokens=4096, source_from=None):
    """
    request_qianfan_v2
    """
    if not prompt:
        return None
    result = None
    # model = "qianfan-lightning-128b-a19b-slim"
    if source_from == "chuangyi":
        appid = "app-0qGP1cWe"
        authorization = "Bearer bce-v3/ALTAK-SAui2P8no9pCoCicO9eEX/6cce29bf1f304c79250bcb3d3436efc7b91b4939"
    elif source_from == "general":
        appid = "app-CdxzgKFY"
        authorization = "Bearer bce-v3/ALTAK-KmUVUm1imukLo7Z1wsmKg/0a78674da950c10655e2c519425f79ff86668267"
    else:
        appid = "app-CdxzgKFY"
        authorization = "Bearer bce-v3/ALTAK-KmUVUm1imukLo7Z1wsmKg/0a78674da950c10655e2c519425f79ff86668267"
    for i in range(MAX_RETRY_TIMES):
        try:
            url = 'https://qianfan.baidubce.com/v2/chat/completions'
            headers = {
                'Content-Type': 'application/json',
                'appid': appid,
                'Authorization': authorization
            }

            if system_prompt:
                messages = [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]

            else:
                messages = [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]

            data = {
                "messages": messages,
                "temperature": 0.8,
                "topp": 0.8,
                "model": model,
                "max_tokens": max_tokens
            }
            time.sleep(i + 2)
            response = requests.post(url, headers=headers, json=data, timeout=10000)
            ret = json.loads(response.text)
            result = ret['choices'][0]['message'] # ['content'] # ['reasoning_content']
            if "reasoning_content" not in result:
                print(f"模型{data['model']}没有推理过程")
            return result['content']
        except Exception as e:
            print(f"请求千帆LLM失败:{e}, 原始响应:{response}, 报错详情:{traceback.print_exc()}")
            print(f"开始重试, {i + 1} / {MAX_RETRY_TIMES}")
            time.sleep(i + 5)
            continue
    print(f"请求千帆LLM {MAX_RETRY_TIMES} 次均失败！")
    return result