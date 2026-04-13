#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
 Copyright (c) 2025 Baidu.com, Inc. All Rights Reserved
"""

import re
import logger.log as log


SENSITIVE_WORDS = [
    "习近平", "李强", "赵乐际", "王沪宁", "蔡奇", "丁薛祥", "李希", "韩正", "李克强",
    "胡锦涛", "温家宝", "毛泽东", "周恩来", "江泽民", "朱镕基", "华国锋", "赵紫阳", "邓小平",
    "中国共产党", "党中央", "中共中央", "总书记", "中共", "中央政治局"
    ]


def contains_sensitive_word(content: str) -> bool:
    """
    检测输入字符串是否包含敏感词表中的任意一个敏感词

    参数:
        content (str): 需要检测的文本内容
    返回:
        bool: 包含敏感词返回True，否则返回False
    """
    if not SENSITIVE_WORDS:  # 空敏感词表直接返回False
        return False

    # 转义特殊字符并用正则表达式或连接
    pattern = re.compile('|'.join(map(re.escape, SENSITIVE_WORDS)))
    return bool(pattern.search(content))


def remove_xhs_emojis(text):
    """
    精准移除小红书表情，格式为 [纯中文字符+R]
    例如：[哭惹R]、[喝奶茶R]，但不会误删 [RefR]、[123R] 等非中文内容
    """
    # 匹配至少一个中文字符 + R 结尾的格式
    return re.sub(r"\[[\u4e00-\u9fff]+R\]", '', text) # re.sub(r'$.*?R$', '', text)


def contains_chinese(text):
    """检查字符串中是否包含中文字符"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def pubilish_time_filter(content):
    """
    从给定内容中过滤掉发布时间字符串。
    
    Args:
        content (str): 包含文本内容的字符串。
    
    Returns:
        str: 过滤掉发布时间字符串后的内容。
    
    """
    publish_time_pattern = r"发布于 20\d{2}-\d{2}-\d{2}"
    match = re.search(publish_time_pattern, content)
    if match:
        return content[:match.start()]
    return content


def post_process(content):
    """
    对文本进行后处理。

    Args:
        content (str): 待处理的文本内容。

    Returns:
        str: 处理后的文本内容。

    """
    # 去掉无关的prompt和思考内容。
    filtered_lines = [line for line in content.split("\n") if not line.startswith("(")]
    content = "\n".join(filtered_lines)

    content = pubilish_time_filter(content)
    content = remove_xhs_emojis(content)
    content = content.replace("  ", "").strip()
    # content = content.replace("\n\n", "\n").strip()
    content = content.lstrip()
    content = content.replace('~', '～').replace('> ', '')
    content = content.replace('标题：', '').replace('标题', '')
    content = content.replace('正文：', '').replace('正文', '')
    content = content.replace('引言', '').replace('结语', '').replace('导语', '')
    content = content.replace('小红书', '').replace('- 小红书', '')
    content = content.replace("* ", "").replace(" *", "").replace("*", "")
    content = re.sub(r'-{2,}', '', content)
    content = content.replace("- ", "").replace(" -", "")
    # 去掉汉字前后和英文字母前后的连字符"-"
    pattern = r'(?<=[\u4e00-\u9fa5a-zA-Z])-|-(?=[\u4e00-\u9fa5a-zA-Z])'
    content = re.sub(pattern, '', content)

    # 去除最后可能出现的#话题
    lines = content.split("\n")
    lines = [part for part in lines]
    new_lines = []
    text_start = False
    for idx, line in enumerate(lines):
        if not text_start and line.strip() != "":
            text_start = True
        if not text_start:
            continue
        if str(line) == '-' or str(line) == '.':
            continue
        if str(line).startswith("：") or str(line).startswith(':'):
            line = str(line)[1:]
        if str(line).startswith(':'):
            line = str(line).strip(':').strip()
        if idx > (len(lines) - 6) and str(line).strip().startswith('#'):
            continue
        # 去全是竖线的行
        temp_line = line.strip().replace('—', '')
        if temp_line.strip() and all(c == '|' for c in temp_line.strip()):
            continue

        # 检测首行如果不包含中文，默认为无效，选择删除
        if idx == 0 and not contains_chinese(line):
            continue
        # 去除行首和行尾的下划线
        line = re.sub(r'^_+|_+$', '', line.strip())
        new_lines.append(line)

    last_valid_index = None
    for i in range(len(new_lines) - 1, -1, -1):
        if new_lines[i].strip() != "":
            last_valid_index = i
            break

    if last_valid_index is not None and \
        (str(new_lines[last_valid_index]).strip().startswith("（") or \
          str(new_lines[last_valid_index]).strip().startswith("(")):
        del new_lines[last_valid_index]
    
    content = "\n".join(new_lines)
    content = content.replace("# ", "").replace("#", "").replace("【】", "")
    return content
