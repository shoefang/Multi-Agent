"""转prompt的文件"""

import re
from typing import List, Dict
from utils.api import request_llm_v2 as request_llm

GRID_TEMPLATE = """
## 网格图像

生成 **一张** 图片，包含最多 4 张幻灯片，按严格的 **2×2 网格** 排列。

这是一个 **固定布局画布**。

最终图像必须始终为完整的 **2×2 网格画布**，
即使提供的幻灯片少于 4 张。

---

## 布局规则（非常重要）

• 画布被划分为 4 个大小相等的象限
• 每个象限尺寸完全一致
• 幻灯片必须严格放置在其指定象限内
• 图像边缘不要留白

网格顺序：

1. 左上
2. 右上
3. 左下
4. 右下

---

## 间距规则

• 象限之间 **不得有任何间距**
• 幻灯片之间 **不得有白色空隙**
• 幻灯片必须边缘紧贴
• 整个网格应呈现为无缝的 2×2 拼贴效果

---

## 当幻灯片数量少于 4 张时

如果幻灯片少于 4 张：

• 不要缩放幻灯片
• 不要拉伸布局
• 保持原始象限尺寸
• 缺失的象限保持为空
• 空白单元必须留空，但尺寸保持一致
• 最终画布尺寸仍必须为完整的 2×2 网格

---

## 视觉一致性

• 所有幻灯片使用相同风格
• 每张幻灯片内部使用相同的内边距
• 使用相同的字体排版
• 使用相同的背景风格

---

## 渲染规则
• **仅渲染实际内容**：标题、正文、视觉元素等用户可见文本
• **禁止渲染**：布局名称（PK卡片/分屏对比/步骤流程等）、结构标签（"标题:"/"类型:"等）、章节标题
• **避免重复**：每段文本仅出现一次，选择最佳位置


## 风格说明

{style_instructions}

宽高比：{aspect_ratio}

{slides_block}
""".strip()

GRID_TEMPLATE_BLACK = """
## 网格图像

生成 **一张** 图像，该图像包含最多 4 张幻灯片，并按照严格的 2×2 网格排列在给你的第一张图片的**白色区域**（该图片已被黑色线条分割）。

---

## 布局规则（非常重要）

给你的第一张图片是一个 **固定布局画布**。你参考这个图的布局进行生成。
即使提供的幻灯片数量少于 4 张，最终生成出来的图像也必须始终是一个完整的 2×2 网格画布，并由黑色线条分割。

• 画布被划分为 4 个大小相等的象限  
• 每个象限尺寸完全一致  
• 幻灯片必须严格放置在给定第一张图片中由**黑色**分割线划分的对应象限内  

网格顺序：
1. 左上
2. 右上
3. 左下
4. 右下

---

## 间距规则

• 象限之间不得留有空隙  
• 幻灯片必须彼此边缘紧贴  
• 各象限必须由可见的黑色（#000000）分割线分开  
• 网格整体应呈现无缝的 2×2 拼贴效果  
• 每一张幻灯片都是一个独立实体，拥有自己的边框，任何元素或文字都不能超出该幻灯片实体的边框  

---

## 当幻灯片少于 4 张时

如果幻灯片数量少于 4 张：

• 不要缩放幻灯片  
• 不要拉伸布局  
• 保持原始象限尺寸  
• 缺失的象限保持为空  
• 空白单元格必须保持空白，但尺寸保持一致  
• 最终画布尺寸仍必须是完整的 2×2 网格，且由黑色线条分割

---

## 视觉一致性

• 所有幻灯片共享相同风格  
• 每张幻灯片内部使用相同的内边距  
• 使用相同的排版风格  
• 使用相同的背景风格  

---

## 文字渲染要求
• **仅渲染实际内容**：核心内容的文字一定要有，视觉元素是可供参考的布局规范/美学设计指导；
• **语义清晰**：使用对比布局/分屏布局时，必须要渲染上对比的主体事物名称，讲清楚谁和谁在对比；
• **禁止渲染**：布局名称（PK卡片/分屏对比/步骤流程等）、结构标签（"标题:"/"类型:"等）、章节标题


## 风格说明
{style_instructions}

宽高比：{aspect_ratio}

{slides_block}
""".strip()


def extract_style_instructions(text: str) -> str:
    """提取风格"""
    m = re.search(r"<STYLE_INSTRUCTIONS>(.*?)</STYLE_INSTRUCTIONS>", text, re.S)
    return m.group(1).strip() if m else ""


def extract_aspect_ratio(text: str) -> str:
    """提取尺寸"""
    m = re.search(r"\*\*Aspect Ratio\*\*:\s*(.+)", text)
    return m.group(1).strip() if m else "1:1"


def split_slides(text: str) -> List[Dict]:
    """
    用更鲁棒的方式找到每个 Slide block：
    - 兼容 \n / \r\n
    - 兼容标题行前后空格
    """
    # 统一换行
    t = text.replace("\r\n", "\n")

    # 找到每个 slide 起点
    pattern = re.compile(r"^##\s*Slide\s+(\d+)\s+of\s+(\d+)\s*$", re.M)
    matches = list(pattern.finditer(t))
    blocks = []

    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(t)
        number = int(m.group(1))
        total = int(m.group(2))
        block_text = t[start:end].strip()
        blocks.append({"number": number, "total": total, "text": block_text})

    return blocks


def extract_section(block: str, section_name: str) -> str:
    """
    抓取 // SECTION_NAME 到下一个 // xxx 或 end
    例如：section_name="KEY CONTENT"
    """
    # e.g. // KEY CONTENT\n ... \n// VISUAL
    m = re.search(
        rf"//\s*{re.escape(section_name)}\s*\n(.*?)(?=\n//\s*[A-Z ]+\s*\n|\Z)",
        block,
        re.S,
    )
    return m.group(1).strip() if m else ""

def _clean_prompt(prompt: str) -> str:
    """清洗prompt，防止Prompt Leakage

    移除会被模型当作文本渲染的结构化标签，保留内容部分。

    Args:
        prompt: 原始prompt

    Returns:
        清洗后的prompt
    """
    # 定义需要保留的内容标签（这些标签帮助模型理解结构，但不应该被渲染）
    # 我们会在开头通过元指令告诉模型不要渲染这些标签
    # 所以这里只移除明显的元数据标签

    patterns_to_clean = [
        r'\*\*Slide \d+:\*\*',           # 移除 **Slide 7:**
        r'\*\*Type\*\*:\s*\w+',          # 移除 **Type**: Detail
        r'\*\*Aspect Ratio\*\*:[^\n]*',  # 移除 **Aspect Ratio**: 1:1
        r'\*\*Goal\`\`\*:',              # 移除 **Narrative Goal**:
    ]

    cleaned = prompt
    for pattern in patterns_to_clean:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    # 清理多余的空行
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)
    cleaned = cleaned.strip()

    return cleaned

def parse_slide_block(block_text: str, number: int, style: str) -> Dict:
    """解析block"""
    slide_type = ""
    m = re.search(r"\*\*Type\*\*:\s*(.+)", block_text)
    if m:
        slide_type = m.group(1).strip()

    # Headline 当作 title
    title = ""
    m = re.search(r"Headline:\s*(.+)", block_text)
    if m:
        title = m.group(1).strip()

    narrative = extract_section(block_text, "NARRATIVE GOAL")
    key_content = extract_section(block_text, "KEY CONTENT")
    visual = extract_section(block_text, "VISUAL")
    reference_image = extract_section(block_text, "REFERENCE IMAGE")
    # LAYOUT 段里通常会有 "Layout: xxx"
    layout_raw = extract_section(block_text, "LAYOUT")
    layout = ""
    m = re.search(r"Layout:\s*(.+)", layout_raw)
    if m:
        layout = m.group(1).strip()
    else:
        layout = layout_raw.strip()

    return {
        "number": number,
        "title": title,
        "type": slide_type,
        "style": style,
        "narrative": narrative,
        "key_content": key_content,
        "visual": visual,
        "layout": layout,
        "reference_image": reference_image
    }

def slide_to_block(s, pos, aspect_ratio, query=None):
    """slide to block"""
    reference_block = f"REFERENCE IMAGE:\n{s['reference_image']}" if s["reference_image"] else ""

    prompt = f"""
    ### 网格位置 {pos}

宽高比：{aspect_ratio}
标题：{s["title"]}
类型：{s["type"]}

传达目标：
{s["narrative"]}

核心内容：
{s["key_content"]}

视觉元素：
{s["visual"]}

布局：
{s["layout"]}
""".strip()
    cleaned_prompt = _clean_prompt(prompt)
    return cleaned_prompt


def generate_prompts(outline_text: str, query=None) -> List[str]:
    """生成"""
    style = extract_style_instructions(outline_text)
    aspect_ratio = extract_aspect_ratio(outline_text)

    slide_blocks = split_slides(outline_text)
    slides = [parse_slide_block(b["text"], b["number"], style) for b in slide_blocks]
    slide_grid = [slide_to_block(s, (pos - 1) % 4 + 1, aspect_ratio, query) for pos, s in enumerate(slides, 1)]
    prompts = []
    for i in range(0, len(slides), 4):
        group = slide_grid[i: i + 4]
        prompt = GRID_TEMPLATE.format(
            style_instructions=style, 
            aspect_ratio=aspect_ratio, 
            slides_block=convert2nanoprompt("\n\n".join(group))
            )
        prompts.append(prompt)
    return prompts, len(slide_grid)


def convert2nanoprompt(original_prompt):
    """转成banana用的prompt"""
    DEEPSEEK_REWRITE_PROMPT = f"""
    你是一个严格的视觉生成指令重写器。

    任务：
    将下面提示词改写为更适合 Nano Banana 理解的连续视觉描述语言。

    ⚠️ 重要区分：

    1. Headline、Sub-headline、Body 中的所有文字
    是“最终必须在幻灯片中逐字渲染的可见文本”。而网格位置、宽高比、标题、类型、传达目标、视觉元素、布局、这些字段只用于指导画面设计，不得作为画面中显示的文字，但是需要保留这些必要的画面设计。

    2. 这些文本：
    - 不得改写
    - 不得同义替换
    - 不得合并
    - 不得删减
    - 不得概括
    - 不得隐藏在视觉元素中
    - 不得被图标语义替代
    - 必须逐字保留

    3. 你只能改写结构说明部分，
    但所有需要渲染的文本必须保持原样。

    严格规则：
    1. 不得删除任何信息
    2. 不得压缩或总结
    3. 不得省略任何视觉细节
    4. 不得添加原文没有的内容
    5. 不改变语义
    6. 仅改写说明性规则语言
    7. 输出为连续视觉描述


    转换原则：
    - 输出结构中，严格保留### 网格位置 i，作为明显的四宫格分界线
    - 将规则改写为最终视觉呈现效果
    - 将禁止项改写为画面仅显示什么
    - Layout(布局) 决定整体画面结构，并且必须保持结构，不允许重新设计布局。
    - 但所有需要渲染的文本必须逐字保留

    输出前必须检查：
    1. 所有 Headline 是否逐字出现
    2. 所有 Sub-headline 是否逐字出现
    3. Body 条目数量是否与原文一致，如果 Body 有 N 条，最终画面必须出现 **N 条原文文本**。

    以下是原始提示词：
    --------------------------------
    {original_prompt}
    --------------------------------

    输出改写后的版本，直接返回改写之后的内容即可，不要有多余的内容：
    """

   #  print("DEEPSEEK_REWRITE_PROMPT:", DEEPSEEK_REWRITE_PROMPT)
    rewrite_prompt = request_llm(DEEPSEEK_REWRITE_PROMPT, model_name="deepseek-v3")
    return rewrite_prompt



    
