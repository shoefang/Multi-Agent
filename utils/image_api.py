#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
 Copyright (c) 2025 Baidu.com, Inc. All Rights Reserved
"""

import json
import time
import io
import urllib
import requests
import os
import sys
import time
import copy
import threading
import base64
import random
import re
import subprocess
import traceback



class BnsClient(object):
    """自定义 BNS 客户端，通过系统命令获取服务实例列表"""
    def __init__(self, bnsname=None):
        """
        初始化
        :param bnsname: BNS 服务名（不含 bns:// 前缀），例如 "group.image-image2text-vl-v3-8861.www.all"
        """
        self.bnsname = bnsname                     # 保存服务名
        self.IP_PORT_LIST = {}                      # 缓存 {服务名: [(ip, port), ...]}
        self.update_time_dict = {}                   # 缓存时间 {服务名: 时间戳(ms)}
        self.TTL_MS = 5 * 1000                        # 缓存有效期 5 秒

    def get_bns_iplist(self, bnsname):
        """
        调用系统命令获取指定 BNS 服务的 IP 列表
        :return: [(ip, port), ...] 列表
        """
        bns_bin = '/noah/bin/get_instance_by_service'
        result = []
        cmd = f"{bns_bin} -ips {bnsname}"
     
        res = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        output = res.stdout.read()
        output = str(output, encoding="utf-8")
        for line in output.strip().split('\n'):
            items = line.strip().split(' ')
            # 格式：实例序号 ip 端口 权重 机房 ...
            if len(items) >= 4 and items[3].isdigit() and int(items[3]) == 0:
                result.append((str(items[1]), int(items[2])))
        return result

    def get_bns_server(self, bnsname):
        """
        获取 BNS 服务实例列表（带缓存）
        :param bnsname: 服务名
        :return: [(ip, port), ...] 列表
        """
        now_ms = int(time.time() * 1000)
        last_update = self.update_time_dict.get(bnsname, 0)
        # 如果缓存存在且未过期，直接返回缓存
        if last_update and (now_ms < last_update + self.TTL_MS):
            return self.IP_PORT_LIST.get(bnsname, [])
        # 否则重新查询
        result = self.get_bns_iplist(bnsname)
        if result:  # 只有获取到结果时才更新缓存
            self.update_time_dict[bnsname] = now_ms
            self.IP_PORT_LIST[bnsname] = result
        return result

    def get_a_host(self, bnsname=None):
        """
        随机返回一个可用的 (ip, port)
        :param bnsname: 如果未提供，使用初始化时保存的服务名
        :return: (ip, port) 元组；如果没有可用实例，返回 (None, None)
        """
        name = bnsname or self.bnsname
        if not name:
            return None, None
        servers = self.get_bns_server(name)
        if not servers:
            return None, None
        return random.choice(servers)



CRAWLER_WRAPPER_BNS_CLIENT_LOCK = threading.Lock()
bns_client = BnsClient()
with CRAWLER_WRAPPER_BNS_CLIENT_LOCK:
    CRAWLER_WRAPPER_BNS_CLIENT = bns_client.get_bns_server("bns://group.image-image2text-vl-v3-8861.www.all")
    search_image_bns_service = bns_client.get_bns_server("bns://group.smartbns-from_product=default%group.blades-gateway-online.ps-wcb.all")
caption_bns_service = CRAWLER_WRAPPER_BNS_CLIENT


class RegexMap(object):
    """
    regex map
    """
    def __init__(self, dic, val=None):
        self.__items = dic
        self.__val = val

    def __getitem__(self, key):
        for regex in self.__items.keys():
            if re.search(regex, key):
                return self.__items[regex]
        return self.__val

def replace_image_url(image_url, temp_dir=None):
    """替换url站点
    """
    to_replace = image_url.split("/")[2]
    url_dict = {
        r"t1[0-5].baidu.com": "yawen-gips.baidu-int.com",
        r"f([7-9]|1[0-2]).baidu.com": "yawen-gips.baidu-int.com",
        r"fc[1-6]tn.baidu.com": "yawen-gips.baidu-int.com",
        r"img[0-2].baidu.com": "yawen-gips.baidu-int.com",
        r"gips[0-3].baidu.com": "yawen-gips.baidu-int.com",
        r"gips.baidu.com": "yawen-gips.baidu-int.com",
        r"img[0-5].imgtn.bdimg.com": "yawen-gips.baidu-int.com",
        r"t[1-4].baidu.com": "yawen-gips.baidu-int.com",
        r"t([7-9]|1[0-5]).baidu.com": "yawen-gips.baidu-int.com",
        r"mms[0-2].baidu.com": "yawen-gips.baidu-int.com",
        ".*\.gips\.baidu\.com": "yawen-gips.baidu-int.com",
        r"simg[0-7].baidu.com": "yawen-gips.baidu-int.com",
        r"imgt[0-9].bdstatic.com": "yawen-gips.baidu-int.com",
        r"i([1-9]|1[0-2]).baidu.com": "yawen-gips.baidu-int.com",
        ".*\.imgtn\.bdimg\.com": "yawen-gips.baidu-int.com",
        r"pics[0-7].baidu.com": "yawen-gips.baidu-int.com",
        r"tiebapic.baidu.com": "yawen-gips.baidu-int.com",
        r"imgsrc.baidu.com": "yawen-gips.baidu-int.com"
    }
    url_map = RegexMap(url_dict, None)
    if url_map[to_replace]:
        image_url = image_url.replace(to_replace, url_map[to_replace])
    return image_url
    # res = requests.get(image_url)
    # if res.status_code == 200:
    #     if temp_dir:
    #         os.makedirs(temp_dir, exist_ok=True)
    #         file_name = image_url.split("/")[-1].split("=")[1].split(",")[0]
    #         temp_file = os.path.join(temp_dir, file_name + '.jpeg')
    #         with open(temp_file, 'wb') as f:
    #             f.write(res.content)
    #         return res, temp_file
    # return res

def parse_json(content):
    """
        解析JSON格式的字符串，并返回一个Python对象。
    如果字符串不是以```json开头或者结尾，则会被剪切。
 
    Args:
        content (str): JSON格式的字符串，可能包含前后的 ```json 和 ``` 标记。
 
    Returns:
        dict: 解析后得到的Python字典对象。
 
    Raises:
        None.
    """

    if content is None:
        return {}
    
    # 确保是字符串
    if not isinstance(content, str):
        content = str(content)
    
    try:
        content = content.strip()
        content = content.replace("\n\n", "\n").strip()\
                        .replace("```json", "").replace("```", "").replace("\n", "")
        return json.loads(content)
   
    except Exception as e:
        print(f"解析json失败:{traceback.format_exc()}，原始内容:{content}")
        return {}
 
 
def encode_image_to_base64(image):
    """
    将本地图片文件编码为Base64格式
 
    Args:
        image_path (str): 图片文件路径
 
    Returns:
        str: Base64编码的图片数据，格式为 data:image/<格式>;base64,<编码>
    """
    try:
        # 检查文件是否存在
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_bytes = buffered.getvalue()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
 
        # 返回完整的Base64数据URI
        return image_base64
 
    except Exception as e:
        print({
            "图片编码失败": traceback.format_exc(),
        })
        return None

def search_image_online(query, num_images=3):
    """
    根据生成的caption对需要检索的图片进行搜索，返回url和desc
    """
    data = {'query': query, "pipe_id": "lite_default", "min_num": num_images}
    blades2_calc_req = {
        "input_data": {
            "text_utf8": json.dumps(data, ensure_ascii=False),
        },
        "user": {
            "user_id": 494,
            "token": "miaobi-business",
            "group_id": 0
        },
        "feat_args": [{
            "feat_id": 8516
        }],
        "trace_header": "11"
    }
    request_json = json.dumps(blades2_calc_req).encode(encoding='UTF8')
    # ip, port = random.choice(server_list)
    #host = search_image_bns_service.get_a_host()
    ip = "10.159.37.19"
    port = "8413"
    for i in range(2):
        try:
            req = urllib.request.Request(
                f"http://{ip}:{port}/BladesService/feat_calc")
            req.add_header('Content-Type', 'application/json')
            response = urllib.request.urlopen(req, request_json, 100)
            res_text = response.read()
            res = json.loads(res_text)
            if res["status"] == "BLADES_STATUS_OK" and \
                    res["feat_res"][0]["feat_detail_status"] == 0:
                value = res["feat_res"][0]["value"]
                value = base64.b64decode(value).decode('utf8')
                inner = json.loads(value)
                results = inner.get('image_res', [{}])
                res = [{"url": r["image_url"], "desc": r["image_info"]["desc"]} for r in results]
                return res
            else:
                print({
                    "request image api failed": res_text,
                    "请求数据": blades2_calc_req,
                    })
                host = search_image_bns_service.get_a_host()
                ip, port = host[0], host[1]
                time.sleep(2 * i)
                continue
        except Exception as e:
            print({
                "搜索图片失败": traceback.format_exc(),
                "请求数据": blades2_calc_req,
            })
            host = search_image_bns_service.get_a_host()
            ip, port = host[0], host[1]
            time.sleep(2 * i)
            continue
    return []
 
def search_image(query, num_images=3):
    """
    根据生成的caption对需要检索的图片进行搜索，返回url和desc
    """
    server = "yq01-sys-rpm316d95bb.yq01.baidu.com:8821"
    feat_id = 8516
    d = {'query': query, "pipe_id": "lite_default", "min_num": num_images}
    text_utf8 = json.dumps(d, ensure_ascii=False)
    blades2_calc_req = {
        "input_data": {
            'text_utf8': text_utf8
            #'text_utf8_arr':text_utf8_arr
        },
        "feat_args": [{
            "feat_id": feat_id
        }],
        "trace_header": "1"
    }
    request_json = json.dumps(blades2_calc_req).encode(encoding='UTF8')
    req = urllib.request.Request(
        "http://{}/Blades2Calculator/calculator_service".format(server))
    req.add_header('Content-Type', 'application/json')
    for i in range(3):
        try:
            response = urllib.request.urlopen(req, request_json, 100)
            res_text = response.read()
            res = json.loads(res_text)
            if res["calc_status"] == "OK" and \
                    res["feat_res"][0]["feat_detail_status"] == 0:
                value = res["feat_res"][0]["value"]
                value = base64.b64decode(res["feat_res"][0]["value"]).decode('utf8')
                inner = json.loads(value)
                results = inner.get('image_res', [{}])
                res = [{"url": r["image_url"], "desc": r["image_info"]["desc"]} for r in results]
                return res
            else:
                print({
                    "request image api failed": res_text
                    })
                continue
        except Exception as e:
            print({
                "搜索图片失败": traceback.format_exc(),
            })
            continue
    return []
 
# class BnsClient(object):
#     """"get bns ip_port list"""
#     def __init__(self):
#         """
#             初始化函数，用于初始化类的属性和方法。
#         初始化完成后，将会创建以下属性：
#             - IP_PORT_LIST: 一个字典，存储每个ip地址对应的端口号列表，格式为 {ip: [port, port, ...], ...}
#             - update_time_dict: 一个字典，存储每个ip地址最近一次更新时间，格式为 {ip: time, ...}
#             - TTL_MS: 一个整数，表示每个ip地址的过期时间，单位是毫秒（ms），默认值为5000ms（5s）
#         """
#         self.IP_PORT_LIST = {}
#         self.update_time_dict = {}
#         self.TTL_MS = 5 * 1000 #ms
        
#     def get_bns_iplist(self, bnsname):
#         """
#             获取指定BNS名称的IP列表，返回一个元组列表，每个元组包含一个IP地址和端口号，格式为（ip, port）。
#         如果端口号不是数字或者不等于0，则不会被添加到结果中。
        
#         Args:
#             bnsname (str): BNS名称，类型为str。
        
#         Returns:
#             list of tuple(str, int): 返回一个元组列表，每个元组包含一个IP地址和端口号，格式为（ip, port）。如果没有找到符合条件的IP，则返回一个空列表。
#         """
#         bns_bin = '/noah/bin/get_instance_by_service'
#         result = []
#         cmd = f"{bns_bin} -ips %s" % bnsname
#         res = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
#         output = res.stdout.read()
#         output = str(output, encoding="utf-8")
#         for ip_port in output.strip().split('\n'):
#             items = ip_port.strip().split(' ')
#             if len(items) >= 4 and items[3].isdigit() and int(items[3]) == 0:
#                 result.append((str(items[1]), int(items[2])))
#         return result
 
#     def get_bns_server(self, bnsname):
#         """
#             获取BNS服务器的IP和端口列表，如果在TTL时间内，则返回上次更新的结果，否则重新查询并更新。
#         如果查询到的结果为空，则不会更新本地缓存。
        
#         Args:
#             bnsname (str): BNS名称，用于标识BNS服务器。
        
#         Returns:
#             list, tuple: 包含BNS服务器IP和端口的元组列表，如果没有找到BNS服务器，则返回一个空列表。
#         """
#         result = []
#         t_now = int(time.time() * 1000)
#         ip_port_create_time = self.update_time_dict.get(bnsname, 0)
#         if ip_port_create_time & (int((ip_port_create_time + self.TTL_MS)) > int(t_now)):
#             result = self.IP_PORT_LIST.get(bnsname, [])
#         else:
#             result = self.get_bns_iplist(bnsname)
#             ip_port_create_time = self.update_time_dict.get(bnsname, 0)
#             if ip_port_create_time & (int((ip_port_create_time + self.TTL_MS)) > int(t_now)):
#                 result = self.IP_PORT_LIST.get(bnsname, [])
#             elif len(result) > 0:
#                 self.update_time_dict[bnsname] = int(time.time() * 1000)
#                 self.IP_PORT_LIST[bnsname] = result
#         return result
# server_list = BnsClient().get_bns_server("group.image-image2text-vl-v3-8861.www.all")
 
def get_caption(image_url, text, server_list=[]):
    """
    req demo
    """
    blades2_calc_req = {
        "input_data": {
            "text_utf8": text,
            "image_url": image_url
        },
        "user": {
            "user_id": 0,
            "token": "debug",
            "group_id": 0
        },
        "feat_args": [{
            "feat_id": 8861
        }],
        "trace_header": "2222"
    }
    request_json = json.dumps(blades2_calc_req).encode(encoding='UTF8')
    # ip, port = random.choice(server_list)
    host = caption_bns_service.get_a_host()
    ip, port = host[0], host[1]
    for i in range(5):
        try:
            server = "{}:{}".format(ip, port)
            uri = "http://{}/Blades2Calculator/calculator_service".format(server)
            response = requests.post(uri, request_json, timeout=300)
            res_text = response.text
            res = json.loads(res_text)
            res_str = base64.b64decode(res.get('feat_res', [])[0].get('value')).decode('utf-8')
            # print(f"返回结果:{res_str}")
            res_data = json.loads(res_str)
            if "output" not in res_data:
                print({
                    "请求图片Caption返回结果错误": res_data,
                    "请求数据": blades2_calc_req,
                })
                host = caption_bns_service.get_a_host()
                ip, port = host[0], host[1]
                time.sleep(5)
                continue
            return res_data
        except Exception as e:
            print({
                "get caption failed": traceback.format_exc(),
                "请求数据": blades2_calc_req,
            })
            # ip, port = random.choice(server_list)
            host = caption_bns_service.get_a_host()
            ip, port = host[0], host[1]
            time.sleep(5)
            continue
    return None


if __name__ == "__main__":
    query = "一张猫咪捕捉鸟的图"
    results = search_image_online(query)
    for r in results:
        print(r)