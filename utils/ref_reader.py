#!/usr/bin/python
# -*- coding: UTF-8 -*-
#############################################################################
#
# Copyright (c) 2021 Baidu.com, Inc. All Rights Reserved
#
#############################################################################
"""

Authors: 
Date: 
File: 

"""

import time
import requests
import json
import base64
import re


def url_hit_keywords(url, special_websites=[]):
    """判断 url 中是否命中 special_websites 中的任意关键词
    """
    if not url or not special_websites:
        return False

    # 对关键词进行正则转义，防止特殊字符影响匹配
    escaped_keywords = [re.escape(k) for k in special_websites]

    # 构造正则：keyword1|keyword2|keyword3
    pattern = re.compile(r'(' + '|'.join(escaped_keywords) + r')', re.IGNORECASE)

    return bool(pattern.search(url))

def req_blades_offline(input_data, feat_id, task_id, user_id=-1, token=""):
    """
    request blades
    param:
        input_data: input_data(dict)
        feat_id: feat_id(int)
        task_id: task_id
        user_id: user_id(int), default 0
        token: token(str), default debug
    return:
        result: str
    """
    msg = ""
    result = None

    blades2_calc_req = {
        "input_data": {
            "text_utf8": json.dumps(input_data)
        },
        "feat_args": [{
            "feat_id": 8898
        }],
        "trace_header": "1"
    }
    max_retry_times = 3
    api_res_list = []
    for retry_time in range(0, max_retry_times):
        time.sleep(0.5 + 2 * retry_time)
        ip, port = "10.35.110.42", "2053" # get_instance_by_service -ip magicPen-online-ref-reader-hba.www.hba 
        blades_url = f"http://{ip}:{port}/Blades2Calculator/calculator_service"

        response = requests.post(blades_url, json.dumps(blades2_calc_req).encode(encoding='UTF8'),
                    headers={"Content-Type": "application/json"},
                    timeout=600)

        # log.notice(f"req res: {response.text}")
        ret = json.loads(response.text)
        # print(ret)
        if ret["calc_status"] == "OK" and \
            ret["feat_res"][0]["feat_detail_status"] == 0:
            result = base64.b64decode(ret["feat_res"][0]["value"])
            try:
                json_bytes = base64.b64decode(result.decode('utf-8'))
                json_string = json_bytes.decode('utf-8')
                api_res_list = json.loads(json_string).get("rerank_docs")

            except Exception as e:
                print(e)
            break

        else:
            msg += response.text + ";"
            print(f"request ref_reader err: {msg}")
            continue

    return api_res_list


def ref_reader(query, display=1, undisplay=3, site=[]):
    """
    检索函数
    """
    api_config = {
            "ak": "0aGmEWUFHvSUoPr6GsOLl74jp4pR9imX",
            "sk": "k3m94UnrelSGBZUdIvuDFE72r0sRNr3g",
            "site": site,
            "bns": "bns://group.smartbns-from_product=api-default%group.flow-api-bfe.NWISE.all",
            "undisplay": undisplay,
            "display": display
        }

    SUCAI_MAX_NUM = display + undisplay
    query_docs = []
    doc_id_list = [] # 根据doc url去重
    str_num = 0        
    ref_text_utf8 = {
        "query": query,
        "task_id": "0",
        "api_config": api_config
    }

    # ref_result = ref_client.req_blades_offline(json.dumps(ref_text_utf8), 8898, "0", 470, "miaobi-8813")
    api_res_list = req_blades_offline(ref_text_utf8, 8898, '0')
    if len(api_res_list) == 0:
        return "没有检索到结果"
    num = 0
    for doc in api_res_list:
        if num >= SUCAI_MAX_NUM:
            break

        if str_num + len(doc['extract']) < 10000 \
            and doc['url'] not in doc_id_list:
            
            if url_hit_keywords(doc["url"], ["baike.baidu"]):
                query_docs.append(doc)
                doc_id_list.append(doc['url'])
                num += 1
                str_num += len(doc['extract'])
                continue

            if url_hit_keywords(doc["url"], ["baidu", "taobao"]):
                continue

            query_docs.append(doc)
            doc_id_list.append(doc['url'])
            num += 1
            str_num += len(doc['extract'])
    
    str_num = 0
    search_results_list = []
    for idx, doc in enumerate(query_docs):
        search_results_list.append("[url: {} ]\n[webpage {} begin]{}[webpage {} end]".format(doc["url"], idx + 1, doc['extract'], idx + 1))

    return search_results_list # "\n".join(search_results_list)





if __name__ == "__main__":
    print(ref_reader("孔子与老子讨论水的道德"))
    # print(req_blades_offline(ref_text_utf8, 8898, '0')[0].keys())
