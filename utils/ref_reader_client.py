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

import sys
import time
import threading
# import lib.bns_client as bns_client
import requests
import json
import base64

CRAWLER_WRAPPER_BNS_CLIENT = None
CRAWLER_WRAPPER_BNS_CLIENT_LOCK = threading.Lock()

class RefReaderClient(object):
    """BNSClient
    """
    def __init__(self, bns="bns://group.smartbns-from_product=default%group.blades-gateway-online.ps-wcb.all"):
        """init
        """
        self.__bns = bns
        self.__max_retry_times = 1
        self._time_out = 600

        # bns client.
        global CRAWLER_WRAPPER_BNS_CLIENT
        global CRAWLER_WRAPPER_BNS_CLIENT_LOCK

        # if CRAWLER_WRAPPER_BNS_CLIENT is None:
        #     with CRAWLER_WRAPPER_BNS_CLIENT_LOCK:
        #         if CRAWLER_WRAPPER_BNS_CLIENT is None:
        #             CRAWLER_WRAPPER_BNS_CLIENT = bns_client.BnsClient(self.__bns)
                    # pass
        # self.bns_service = CRAWLER_WRAPPER_BNS_CLIENT

    def get_host(self):
        """
            获取一个主机，并返回。如果没有可用的主机，则抛出异常。
        该方法会被自动调用，无需手动调用。
        
        Args:
            None
        
        Returns:
            str (required): 一个字符串类型的主机地址，例如 '192.168.0.1'。
        
        Raises:
            None
        """
        host = self.bns_service.get_a_host()
        return host

    def __gen_blades_req(self, input_data, feat_id, user_id=0, token=""):
        """
        生成千仞请求
        """
        req_obj = {}
        req_obj["user"] = {"user_id": user_id, "token": token, "group_id": 0}
        req_obj["feat_args"] = [{"feat_id": feat_id}]
        req_obj["input_data"] = input_data
        req_obj["log_id"] = 0
        return req_obj

    def req_blades(self, input_data, feat_id, task_id, user_id=-1, token=""):
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
        input_data = {"text_utf8": input_data}
        for retry_time in range(0, self.__max_retry_times):
            time.sleep(0.5 + 2 * retry_time)
            blades_req_data = self.__gen_blades_req(input_data, feat_id, user_id, token)
            ip, port = self.get_host()
            blades_url = f"http://{ip}:{port}/BladesService/feat_calc"

            response = requests.post(blades_url, json.dumps(blades_req_data).encode(encoding='UTF8'),
                        headers={"Content-Type": "application/json"},
                        timeout=self._time_out)
            ret = json.loads(response.text)
            if "status" not in ret or ret["status"] != "BLADES_STATUS_OK":
                msg += response.text + ";"
                continue

            elif ret["feat_res"][0]["feat_detail_status"] != 0:
                msg += ret["feat_res"][0]["feat_detail_status"] + ";"
                continue

            else:
                result = base64.b64decode(ret["feat_res"][0]["value"])
                break

        return result

    def req_blades_offline(self, input_data, feat_id, task_id, user_id=-1, token=""):
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
                "text_utf8": input_data
            },
            "feat_args": [{
                "feat_id": 8898
            }],
            "trace_header": "1"
        }

        for retry_time in range(0, self.__max_retry_times):
            time.sleep(0.5 + 2 * retry_time)
            ip, port = "10.61.221.32", "8323"
            blades_url = f"http://{ip}:{port}/Blades2Calculator/calculator_service"

            response = requests.post(blades_url, json.dumps(blades2_calc_req).encode(encoding='UTF8'),
                        headers={"Content-Type": "application/json"},
                        timeout=self._time_out)

            ret = json.loads(response.text)
            if ret["calc_status"] == "OK" and \
                ret["feat_res"][0]["feat_detail_status"] == 0:
                result = base64.b64decode(ret["feat_res"][0]["value"])
                break

            else:
                msg += response.text + ";"
                continue

        return result
