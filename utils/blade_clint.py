#!/usr/bin/env python
# -*- coding: utf-8 -*-
########################################################################
# 
# Copyright (c) 2025 Baidu.com, Inc. All Rights Reserved
# 
########################################################################
"""
Blades请求处理模块
 
该模块提供了与Blades服务交互的客户端功能，包括BNS服务发现和请求发送。
"""
 
import requests
import json
import time
import base64
import random
import subprocess



def gen_blades_req(input_data, feat_id, user_id=0, token=""):
    """
    构造千仞请求
    """
    req_obj = {}
    req_obj["user"] = {"user_id": user_id, "token": token, "group_id": 0}
    req_obj["feat_args"] = [{"feat_id": feat_id}]
    req_obj["input_data"] = {"text_utf8": json.dumps(input_data, ensure_ascii=False)}
    req_obj["log_id"] = str(feat_id)
    return req_obj

# 千仞线上请求
def online_request(input_data,
                    feat_id=9080,
                    user_id=495, 
                    token='baikan-ttv', 
                    bns_name="group.smartbns-from_product=default%group.blades-gateway-online.ps-wcb.all",
                    timeout=600,
                    max_retries=1):
    """
    online_request
    """
    blades_req_data = gen_blades_req(input_data, feat_id, user_id, token)
    server_list = BnsClient().get_bns_server(bns_name)
    ip, port = random.choice(server_list)
    blades_url = f"http://{ip}:{port}/BladesService/feat_calc"
    for attempt in range(max_retries):
       
        response = requests.post(url=blades_url, json=blades_req_data,
                headers={"Content-Type": "application/json"},
                timeout=timeout)
        response.raise_for_status()
        return response.text

    
    if attempt >= max_retries:
        raise Exception(f"{max_retries}次千仞请求均失败！")


# 获取网址
def getip(bns):
    """
    获取ip
    """
    server_list = BnsClient().get_bns_server(bns)
    ip, port = random.choice(server_list)
    blades_url = f"{ip}:{port}"

    return blades_url

# 线上请求：获取tts
def get_tts_online(input_data):
    """
    线上请求tts
    """
    feat_id = 9041
    user_id = 489
    token = "ad-video-gen"
    bns_name = "group.smartbns-from_product=default%group.blades-gateway-online.ps-wcb.all"

    return online_request(input_data, feat_id, user_id, token, bns_name)


# 线上请求：获取bgm
def get_bgm_online(content):
    """
    获取线上bgm
    """
    input_data = {
        'project': 'ads',
        'content': content,
    }
    feat_id = 9080
    user_id = 489
    token = "ad-video-gen"
    bns_name = "group.smartbns-from_product=default%group.blades-gateway-online.ps-wcb.all"
    try:
        start_time = time.time()
        res = online_request(input_data, feat_id, user_id, token, bns_name)
        res = json.loads(res).get("feat_res", [])[0].get("value")
        res = base64.b64decode(res).decode('utf-8')
        res = json.loads(res)
        return res['selected_bgm_url']
    except Exception as e:
        raise Exception(f"获取bgm失败, content={content}, 异常信息:{e}")


# 临时离线请求：获取tts
def make_request_tts(input_data):
    """
    请求tts
    """
    #ip, port = get_bns_iplist("group.video-gen-general-pipeline-tts-9041-online.www.all")
    ip, port = '10.190.192.25', '8822'
    url = "http://{}:{}/Blades2Calculator/calculator_service".format(ip, port)
    
    blades2_calc_req = {
        "user": {
            "user_id": 477,
            "group_id": 0,
            "token": "baikan-9067"
        },
        "log_id": "9041",
        "input_data": {
            "text_utf8": json.dumps(input_data, ensure_ascii=False),
        },
        "feat_args": [{"feat_id": 9041}]  
    }

    try:
        response = requests.post(url=url, json=blades2_calc_req, timeout=8000)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print("Request failed: {}".format(e))
        return None


class BnsClient(object):
    """BNS客户端，用于获取服务IP和端口列表"""
    
    def __init__(self):
        """初始化BNS客户端
        
        Attributes:
            IP_PORT_LIST (dict): 存储每个IP地址对应的端口号列表
            update_time_dict (dict): 存储每个IP地址最近一次更新时间
            TTL_MS (int): IP地址过期时间，单位毫秒，默认5000ms
        """
        self.IP_PORT_LIST = {}
        self.update_time_dict = {}
        self.TTL_MS = 5 * 1000  # ms
 
    def get_bns_iplist(self, bnsname):
        """获取指定BNS名称的IP列表
        
        Args:
            bnsname: BNS名称
            
        Returns:
            包含(IP地址, 端口号)元组的列表，格式为[(ip, port), ...]
            如果没有找到符合条件的IP，则返回空列表
        """
        bns_bin = '/noah/bin/get_instance_by_service'
        result = []
        cmd = "{} -ips {}".format(bns_bin, bnsname)
        res = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        output = res.stdout.read()
        output = str(output, encoding="utf-8")
        for ip_port in output.strip().split('\n'):
            items = ip_port.strip().split(' ')
            if len(items) >= 4 and items[3].isdigit() and int(items[3]) == 0:
                result.append((str(items[1]), int(items[2])))
        return result
 
    def get_bns_server(self, bnsname):
        """获取BNS服务器的IP和端口列表
        
        如果在TTL时间内，则返回上次更新的结果，否则重新查询并更新。
        如果查询到的结果为空，则不会更新本地缓存。
        
        Args:
            bnsname: BNS名称，用于标识BNS服务器
            
        Returns:
            包含BNS服务器IP和端口的元组列表，如果没有找到BNS服务器，则返回空列表
        """
        result = []
        t_now = int(time.time() * 1000)
        ip_port_create_time = self.update_time_dict.get(bnsname, 0)
        if ip_port_create_time & (int((ip_port_create_time + self.TTL_MS)) > int(t_now)):
            result = self.IP_PORT_LIST.get(bnsname, [])
        else:
            result = self.get_bns_iplist(bnsname)
            ip_port_create_time = self.update_time_dict.get(bnsname, 0)
            if ip_port_create_time & (int((ip_port_create_time + self.TTL_MS)) > int(t_now)):
                result = self.IP_PORT_LIST.get(bnsname, [])
            elif len(result) > 0:
                self.update_time_dict[bnsname] = int(time.time() * 1000)
                self.IP_PORT_LIST[bnsname] = result
        return result
 
 
class BladesClient(object):
    """Blades服务客户端"""
    
    def __init__(self, args):
        """初始化Blades客户端
        
        Args:
            args (dict): 包含初始化所需参数的字典
            
        Attributes:
            _url (str): 请求的URL地址
            _user_id (int): 用户ID
            _token (str): 请求的认证令牌
            _max_retry (int): 最大重试次数
            _time_out (int): 请求超时时间（秒）
        """
        self._url = str(args.get("url", 
                "group.video-gen-general-pipeline-txteffect-9044-online.www.all"))
        self._user_id = int(args.get("user_id", 483))
        self._token = str(args.get("token", "chuangyi-8916"))
        self._max_retry = int(args.get("retry_times", 3))
        self._time_out = int(args.get("time_out_s", 300))
 
    def __gen_blades_req(self, input_data, feat_id, user_id=0, token=""):
        """生成千仞请求数据
        
        Args:
            input_data (dict): 输入数据
            feat_id (int): 特征ID
            user_id (int, optional): 用户ID，默认为0
            token (str, optional): 认证令牌，默认为空字符串
            
        Returns:
            dict: 生成的请求数据
        """
        if user_id == -1:
            user_id = self._user_id
        if token == "":
            token = self._token
        req_obj = {}
        req_obj["user"] = {"user_id": user_id, "token": token, "group_id": 0}
        req_obj["feat_args"] = [{"feat_id": feat_id}]
        req_obj["input_data"] = {"text_utf8": input_data}
        req_obj["log_id"] = "1243"
        return req_obj
 
    def req_blades(self, input_data, feat_id, task_id, user_id=-1, token=""):
        """发送Blades请求
        
        Args:
            input_data (dict): 输入数据
            feat_id (int): 特征ID
            task_id (int): 任务ID
            user_id (int, optional): 用户ID，默认为-1
            token (str, optional): 认证令牌，默认为空字符串
            
        Returns:
            bytes: 请求结果数据，如果请求失败则返回None
            
        Raises:
            Exception: 当请求过程中出现异常时抛出
        """
        msg = ""
        input_tokens = -1
        output_tokens = -1
        result = None
 
        try:
            blades_req_data = self.__gen_blades_req(input_data, feat_id, user_id, token)
            server_list = BnsClient().get_bns_server(self._url)
            ip, port = random.choice(server_list)
            # ip, port = '10.108.240.13', '8126' #
            blades_url = "http://{}:{}/Blades2Calculator/calculator_service".format(ip, port)
            print(blades_url)
            response = requests.post(blades_url, json.dumps(blades_req_data).encode(encoding='UTF8'),
                        headers={"Content-Type": "application/json"},
                        timeout=self._time_out)
            ret = json.loads(response.text)
            print("return responce:", ret)
        
            result = base64.b64decode(ret["feat_res"][0]["value"])
            result = base64.b64decode(result.decode('utf-8')).decode('utf-8')
            return result
            
        except Exception as e:
            msg += str(e) + ";"
            print("msg", msg)
 
        return result
    
