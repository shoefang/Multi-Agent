import requests
import json
import os
import sys
import time
import copy
import threading
import base64
import random
import subprocess
import pandas as pd

class BnsClient(object):
    """"get bns ip_port list"""
    def __init__(self):
        """
            初始化函数，用于初始化类的属性和方法。
        初始化完成后，将会创建以下属性：
            - IP_PORT_LIST: 一个字典，存储每个ip地址对应的端口号列表，格式为 {ip: [port, port, ...], ...}
            - update_time_dict: 一个字典，存储每个ip地址最近一次更新时间，格式为 {ip: time, ...}
            - TTL_MS: 一个整数，表示每个ip地址的过期时间，单位是毫秒（ms），默认值为5000ms（5s）
        """
        self.IP_PORT_LIST = {}
        self.update_time_dict = {}
        self.TTL_MS = 5 * 1000 #ms
        
    def get_bns_iplist(self, bnsname):
        """
            获取指定BNS名称的IP列表，返回一个元组列表，每个元组包含一个IP地址和端口号，格式为（ip, port）。
        如果端口号不是数字或者不等于0，则不会被添加到结果中。
        
        Args:
            bnsname (str): BNS名称，类型为str。
        
        Returns:
            list of tuple(str, int): 返回一个元组列表，每个元组包含一个IP地址和端口号，格式为（ip, port）。如果没有找到符合条件的IP，则返回一个空列表。
        """
        bns_bin = '/noah/bin/get_instance_by_service'
        result = []
        cmd = f"{bns_bin} -ips %s" % bnsname
        res = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        output = res.stdout.read()
        output = str(output, encoding="utf-8")
        for ip_port in output.strip().split('\n'):
            items = ip_port.strip().split(' ')
            if len(items) >= 4 and items[3].isdigit() and int(items[3]) == 0:
                result.append((str(items[1]), int(items[2])))
        return result
 
    def get_bns_server(self, bnsname):
        """
            获取BNS服务器的IP和端口列表，如果在TTL时间内，则返回上次更新的结果，否则重新查询并更新。
        如果查询到的结果为空，则不会更新本地缓存。
        
        Args:
            bnsname (str): BNS名称，用于标识BNS服务器。
        
        Returns:
            list, tuple: 包含BNS服务器IP和端口的元组列表，如果没有找到BNS服务器，则返回一个空列表。
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
    """
    blades client
    """

    def __init__(self, args):
        self._url = str(args.get("url", \
                "group.smartbns-from_product=default%group.blades-gateway-online.ps-wcb.all"))
        self._user_id = int(args.get("user_id", 0))
        self._token = str(args.get("token", 0))
        self._max_retry = int(args.get("retry_times", 3))
        self._time_out = int(args.get("time_out_s", 600))

    def __gen_blades_req(self, input_data, feat_id, user_id=0, token=""):
        """
        生成千仞请求
        """
        if user_id == -1:
            user_id = self._user_id
        if token == "":
            token = self._token
        req_obj = {}
        req_obj["user"] = {"user_id": user_id, "token": token, "group_id": 0}
        req_obj["feat_args"] = [{"feat_id": feat_id}]
        req_obj["input_data"] = input_data
        req_obj["log_id"] = "1243"

        return req_obj

    def req_blades(self, input_data,  feat_id = 9041,user_id=477, token="baikan-9067"):
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
        for retry_time in range(0, self._max_retry):
            time.sleep(0.5 + 2 * retry_time)
            blades_req_data ={
                "user": {
                    "user_id": user_id,
                    "group_id": 0,
                    "token": token
                },
                "log_id":"9041",
                "input_data": {
                    "text_utf8": json.dumps(input_data, ensure_ascii=False),
                },
                "feat_args": [{"feat_id": feat_id}]  
            }

            ip, port = '10.144.182.25', '2005'
            blades_url = f"http://{ip}:{port}/Blades2Calculator/calculator_service"


            
            # 服务接收的输入
            blades_req_data = {
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

            print(blades_req_data)
            try:
                response = requests.post(url=blades_url, json=blades_req_data, timeout=8000)
                response.raise_for_status()  # Raise an error for bad responses
                
            except requests.exceptions.RequestException as e:
                print("Request failed: {}".format(e))

            
            ret = json.loads(response.text)
            ret = response.json()
            if "calc_status" not in ret or ret["calc_status"] != "OK":
                msg += response.text + ";"
                print(response.text)
                continue
            elif ret["feat_res"][0]["feat_detail_status"] != 0:
                msg += str(ret["feat_res"][0]["feat_detail_status"]) + ";"
                print(ret)
                continue
            else:
                # print (ret["feat_res"][0]["value"])
                result = base64.b64decode(ret["feat_res"][0]["value"])
                result = json.loads(result)
                print(result)        
                return result         

        return result

client = BladesClient({"url": "group.video-gen-general-pipeline-tts-9041-online.www.all"})


def download_file(url: str, filepath: str) -> str:
    """下载文件到临时目录"""
    dirname = os.path.dirname(filepath)
    os.makedirs(dirname, exist_ok=True)
    try:
        local_path = filepath
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"下载完成: {filepath}")
        return local_path
    except Exception as e:
        print(f"下载文件失败 {url}: {e}")
        raise


def process(slices, audio_save_dir,spd=5.0):
    voice_dic = slices["characters_voices"]
    
    text_list = []
    for i, shot in enumerate(slices['shots'], 1):
        audio_save_path = os.path.join(audio_save_dir,f'分镜{i}.mp3')
        if os.path.exists(audio_save_path):
            continue
        line = shot["line"]
        if line == "":
            continue
        text_list.append(line)
        data = {
            "business": "test",
            "mid": voice_dic[shot["speaker"]],
            "pit": 5.0, # 选填，指定音调
            "spd": spd, # 选填，指定语速
            "audio_text_list": [line]
        }

        # input_data = {"text_utf8": json.dumps(data, ensure_ascii=False)}
        res = client.req_blades(data, 9041)
        if res is None:
            print("没有旁白")
            continue

        

        shot["speech"] = res["audio_sentence_url_list"][0]
        shot["audio_duration"] = res["audio_sentence_duration_list"][0]
        shot["duration"] = round(shot["audio_duration"]+1)
        
    return slices


def process_comic(slices, audio_save_dir,spd=5.0):
    voice_dic = slices["characters_voices"]
    
    text_list = []
    for i, shot in enumerate(slices['shots'], 1):
        audio_save_path = os.path.join(audio_save_dir,f'分镜{i}.mp3')
        if os.path.exists(audio_save_path):
            continue
        line = shot["line"]
        if line == "":
            continue
        text_list.append(line)
        data = {
            "business": "test",
            "mid": voice_dic[shot["speaker"]],
            "pit": 5.0, # 选填，指定音调
            "spd": spd, # 选填，指定语速
            "audio_text_list": [line]
        }

        # input_data = {"text_utf8": json.dumps(data, ensure_ascii=False)}
        res = client.req_blades(data, 9041)
        if res is None:
            print("没有旁白")
            continue

        shot["speech"] = res["audio_sentence_url_list"][0]
        shot["audio_duration"] = res["audio_sentence_duration_list"][0]
        shot["duration"] = round(shot["audio_duration"]+1)
        
    return slices


def save_slices(slices, save_dir):
    """保存分镜数据到JSON文件，排除frame字段"""
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, "slices.json")
    with open(file_path, "w", encoding='utf-8') as file:
        json.dump(slices, file, ensure_ascii=False, indent=4)
    print(f"slices数据已保存至: {file_path}")





if __name__ == "__main__":
    slices_dir = "/Users/lihuining01/Desktop/广告视频/1029_ad_video2/slices_test"
    save_dir = "/Users/lihuining01/Desktop/广告视频/1029_ad_video2/output/1103_slices_test"
    tts_save_dir = os.path.join(save_dir, "tts_result")
    
    
    for slice_id in all_tts_results:
        for digital_id in all_tts_results[slice_id]:
            wavfile_path = os.path.join(tts_save_dir, f"{slice_id}_{digital_id}.wav")
            download_file(all_tts_results[slice_id][digital_id], wavfile_path)

