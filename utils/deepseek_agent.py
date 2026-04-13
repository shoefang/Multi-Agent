#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
 Copyright (c) 2025 Baidu.com, Inc. All Rights Reserved
"""

import sys
import socket
import requests
import json
import time
import threading
import re
import base64
from blade_clint import BnsClient as bns_client

CRAWLER_WRAPPER_BNS_CLIENT = None
CRAWLER_WRAPPER_BNS_CLIENT_LOCK = threading.Lock()

class DSAgent(object):
    """DSAgent
    """
    def __init__(self, bns="bns://group.smartbns-from_product=default%group.blades-gateway-online.ps-wcb.all"):
        """init
        """
        self.__bns = bns
        self.__max_retry_times = 3

        # self.ip = socket.gethostbyname(socket.gethostname())

        # bns client.
        global CRAWLER_WRAPPER_BNS_CLIENT
        global CRAWLER_WRAPPER_BNS_CLIENT_LOCK

        if CRAWLER_WRAPPER_BNS_CLIENT is None:
            with CRAWLER_WRAPPER_BNS_CLIENT_LOCK:
                if CRAWLER_WRAPPER_BNS_CLIENT is None:
                    CRAWLER_WRAPPER_BNS_CLIENT = bns_client.BnsClient(self.__bns)
                    # pass
        self.bns_service = CRAWLER_WRAPPER_BNS_CLIENT


    def request(self, user_prompt, sys_prompt=None, model="deepseek-r1", max_tokens=4096, source_from=None):
        """request deepseek
        """
        headers = {
            'Content-Type': 'application/json'
        }
        if source_from == "general":
            token = "miaobi-8813"
        else:
            token = "miaobi-8813"

        if sys_prompt:
            messages = [{
                "role": "system",
                "content": sys_prompt
                },
                {
                "role": "user",
                "content": user_prompt
                }
            ]
        else:
            messages = [{
                "role": "user",
                "content": user_prompt
                }
            ]

        post_dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": 0.8
        }


        text_utf8 = json.dumps(post_dict)
        blades2_calc_req = {
            "input_data": {
                "text_utf8": text_utf8
            },
            "user": {
                "user_id": 470,
                "group_id": 0,
                "token": token
            },
            "feat_args": [{
                "feat_id": 8775
            }],
            "log_id": 1243
        }

        request_json = json.dumps(blades2_calc_req).encode(encoding='UTF8')
        for retry_times in range(self.__max_retry_times):
            time.sleep(retry_times)
            host = self.bns_service.get_a_host()
            # host = ["10.159.39.17", "8002"]
            url = "http://{}:{}/BladesService/feat_calc".format(host[0], str(host[1]))
            try:
                response = requests.post(url, headers=headers, data=request_json, timeout=300)
                if response.status_code != 200:
                    
                   
                    continue

                resp = response.json()
                if resp["status"] == "BLADES_STATUS_OK" and \
                        resp["feat_res"][0]["feat_detail_status"] == 0:
                    value = resp["feat_res"][0]["value"]
                    value = json.loads(base64.b64decode(resp["feat_res"][0]["value"]))
                    return value['choices'][0]['message']

                else:
                    
                    continue

            except Exception as e:
                
                continue
                          

        return None


def main():
    """
    main test
    """

    ds_agent = DSAgent("group.blades3-gateway.superpage.all")
    print(ds_agent.request("1+1等于几"))

if __name__ == "__main__":
    main()
