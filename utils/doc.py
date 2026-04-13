#!/usr/bin/python
# -*- coding: UTF-8 -*-
#############################################################################
#
# Copyright (c) 2021 Baidu.com, Inc. All Rights Reserved
#
#############################################################################
"""

Authors: 
Date: 2025/06/03 15:12:12
File: doc.py

"""
import json
import os
from copy import deepcopy
import logging as log
import re
import datetime

class Doc(object):
    """Doc
    """
    def __init__(self):
        """init
        """
        self.__inited = False
        
        self.type = None #int
        self.query = ""
        self.url = ""
        self.site = ""
        self.dx_level = 0 #int
        self.source_type = None #int
        self.title = ""
        self.sentence = []
        self.content = ""
        self.qu_score = ""
        self.extract = ""
        self.doc_ori = {}
        self.doc_authority_model_score = -1
        self.dqa_trust_level = -1
        self.page_time = -1
        self.page_time_str = "时间未知"
        self.dqa_trust_level_str = ""
        self.doc_authority_str = ""

    def __purify_content(self, sentence):
        """__purify_content
        """
        if not sentence:
            return ""

        content = " ".join(sentence)
        if self.site == "www.xiaohongshu.com":
            # 去除产品名称
            content = content.replace(" - 小红书", "").replace("- 小红书", "").replace(" -小红书", "").replace("-小红书", "")

            # 去除话题标签
            content = re.sub('#[^ ]*', '', content)

            # 去除xhs emoji
            content = re.sub(r"\[[\u4e00-\u9fff]+R\]", '', content)

            content = content.strip()

        else:
            re_sub_list = [
                r'网页新闻贴吧知道网盘图片视频地图文库资讯采购百科\s+百度首页\s+登录\s+注册\s+进入词条全站搜索帮助\s+进入词条\s+播报编辑讨论\s+\d+\+?收藏赞\s+登录\s+首页\s+历史上的今天\s+百科冷知识\s+图解百科\s+秒懂百科\s+懂啦\s+秒懂本尊答\s+秒懂大师说\s+秒懂看瓦特\s+秒懂五千年\s+秒懂全视界\s+特色百科\s+数字博物馆\s+非遗百科\s+恐龙百科\s+多肉百科\s+艺术百科\s+科学百科\s+知识专题\s+加入百科\s+新人成长\s+进阶成长\s+任务广场\s+百科团队\s+校园团\s+分类达人团\s+热词团\s+繁星团\s+蝌蚪团\s+权威合作\s+合作模式\s+常见问题\s+联系方式\s+个人中心\s+.*?\s+播报编辑讨论\d+\+?上传视频',
                r'©\s*\d*\s*Baidu\s+使用百度前必读.*?京ICP证030173号\s+京公网安备11000002000001号',
                r'京ICP证030173号\s+京公网安备11000002000001号',
                r'网页新闻贴吧知道网盘图片视频地图文库资讯采购'
            ]

            for _sub_re in re_sub_list:
                content = re.sub(_sub_re, "", content)
            content = content.strip()

        return content
    
    def get_content_length(self):
        """get pure content length"""
        return len(self.content) - len(self.title)

    def is_inited(self):
        """is_inited
        """
        return self.__inited

    def deserialize_from_dict(self, query, doc):
        """deserialize_from_dict
        """
        if self.__inited:
            log.fatal("already inited")
            return False

        self.__inited = True
        try:
            self.query = query
            self.type = doc["type"]
            self.url = doc["url"]
            
            url_sub = re.sub("^https://", "", re.sub("^http://", "", self.url))
            url_sub_list = url_sub.split("/")
            self.site = url_sub_list[0]

            self.dx_level = doc["dx_level"]
            self.source_type = doc["source_type"]
            self.title = doc["title"]
            self.sentence = doc["sentence"]
            self.dqa_trust_level = doc["dqa_trust_level"]
            self.doc_authority_model_score = doc["doc_authority_model_score"]
            self.content = self.__purify_content(self.sentence)
            self.doc_ori = doc
            self.page_time = doc["page_time"]
            self.not_displayable = doc.get("not_displayable", False)
            try:
                if self.page_time > 1:
                    self.page_time_str = datetime.datetime.fromtimestamp(self.page_time)
                    self.page_time_str = self.page_time_str.strftime('%Y年%m月%d日')

            except:
                log.fatal(f"{self.url} get page_time_str error!")

            if self.doc_authority_model_score <= 70:
                self.doc_authority_str = "权威性弱"

            else:
                self.doc_authority_str = "权威性强"

            if self.dqa_trust_level == 2:
                self.dqa_trust_level_str = "素材来源比较可信"

            elif self.dqa_trust_level > 2:
                self.dqa_trust_level_str = "素材来源非常可信"

            else:
                self.dqa_trust_level_str = "素材来源可信度一般"


        except Exception as e:
            log.fatal(f"serialize_from_dict failed, {e}, query={query}, doc={doc}")
            return False

        return True

    def serialize_to_dict(self):
        """serialize_to_dict
        """
        _dict = {
            "query": self.query,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "qu_score": self.qu_score,
            "dx_level": self.dx_level,
            "extract": self.extract,
            "not_displayable": self.not_displayable,
            # "doc_ori": self.doc_ori,
            "dqa_trust_level": self.dqa_trust_level,
            "doc_authority_model_score": self.doc_authority_model_score,
            "dqa_trust_level_str": self.dqa_trust_level_str,
            "doc_authority_str": self.doc_authority_str,
            "page_time_str": self.page_time_str
        }
        return _dict