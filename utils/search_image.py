"""图片检索"""

import os
import json
import urllib
import base64
import requests
from PIL import Image
from io import BytesIO
import re

import requests


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

def get_image(image_url):
    """下载图片"""
    to_replace = image_url.split("/")[2]
    url_dict = {
        r"t[1-4].baidu.com": "yawen-gips.baidu-int.com",
        r"t([7-9]|1[0-5]).baidu.com": "yawen-gips.baidu-int.com",
        r"t1[0-5].baidu.com": "yawen-gips.baidu-int.com",
    }
    image_url = image_url.replace(to_replace, "yawen-gips.baidu-int.com")
    response = requests.get(image_url)
    if response.status_code == 200:
        # 使用BytesIO将图片内容转为字节流
        image_data = BytesIO(response.content)

        # 使用PIL打开字节流中的图片
        image = Image.open(image_data)
        return image
    else:
        return None

def search_images(query):
    """
    blades_req
    """
    server = "yq01-sys-rpm316d95bb.yq01.baidu.com:8821"
    feat_id = 8516
    #通用产线
    d = {'query': query, "pipe_id": "lite_default"}
    #id映射表：https://ku.baidu-int.com/knowledge/HFVrC7hq1Q/RXAdS2dkN0/IiZGTPWrUX/f3AB64Q-suFbEY

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
    try:
        response = urllib.request.urlopen(req, request_json, 100)
        res_text = response.read()
        res = json.loads(res_text)
        if res["calc_status"] == "OK" and \
                res["feat_res"][0]["feat_detail_status"] == 0:
            value = res["feat_res"][0]["value"]
            value = base64.b64decode(res["feat_res"][0]["value"]).decode('utf8')
            res = json.loads(value)["image_res"][0]
            url = res["image_url"]
            return url
        else:
            print("NOT OK!? Response is:")
            print(res_text)
    except Exception as e:
        print(str(e))


if __name__ == "__main__":
    url = search_images("山姆 芝士牛肉卷")
    print(url)

    