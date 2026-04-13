"""转提示词"""

import re
from typing import List, Dict


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
    res = m.group(1).strip() if m else ""
    if section_name == "REFERENCE IMAGE" and len(res):
        pattern = re.compile(r'\[(.*?)\](https?://\S+)')
    
        results = []
        for line in res.splitlines():
            match = pattern.search(line.strip())
            if match:
                caption = match.group(1)
                url = match.group(2)
                results.append({"caption": caption, "url": url})
        print(results)
        return results
    return res

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
    """parse each slide"""
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

def slide_to_prompt(slide, aspect_ratio, query=None):
    """convert it to prompt"""
    style_instructions = slide.get("style", "")
    narrative_goal = slide.get('narrative_goal', '')
    key_content = slide.get('key_content', '')
    visual_desc = slide.get('visual', '')
    layout_info = slide.get('layout', '')
    slide_title = slide.get('title', '')
    reference_image = slide.get("reference_image", "")

    if len(reference_image):
        image_captions = "\n".join([f"图{i+1}: " + r["caption"] for i, r in enumerate(reference_image)])
    else:
        image_captions = ""


    prompt = f"""
[用户查询上下文]
{query if query else '无'}

【渲染规则】
- **仅渲染实际内容**：标题、正文、视觉元素等用户可见文本
- **禁止渲染**：布局名称（PK卡片/分屏对比/步骤流程等）、结构标签（"标题:"/"类型:"等）、章节标题
- **避免重复**：每段文本仅出现一次，选择最佳位置
- **参考图注入**：当有参考图注入时，整体画面布局要考虑参考图，保持美观。

---

按照以下规范创建专业演示幻灯片：

## 风格说明

{style_instructions}

---

## 幻灯片内容

**标题**: {slide_title}

**目标**: {narrative_goal}

**核心内容**:
{key_content}

**视觉元素**:
{visual_desc}

**布局指南**:
{layout_info}

**宽高比**: {aspect_ratio}

**参考图**:
{image_captions}

---

立即生成幻灯片图像。严格遵循所有风格指南。

**记住**：仅渲染实际内容，不渲染布局名/结构标签/章节标题，避免重复。
""".strip()

    if not len(image_captions):
        prompt = prompt.replace("**参考图**", "")
    cleaned_prompt = _clean_prompt(prompt)
    return cleaned_prompt


def generate_prompts(outline_text: str, query=None) -> List[str]:
    """generate prompt"""
    style = extract_style_instructions(outline_text)
    aspect_ratio = extract_aspect_ratio(outline_text)

    slide_blocks = split_slides(outline_text)
    slides = [parse_slide_block(b["text"], b["number"], style) for b in slide_blocks]
    prompts = [slide_to_prompt(s,  aspect_ratio, query) for s in slides]
    reference_image = []
    for s in slides:
        if not len(s["reference_image"]):
            reference_image.append([])
        else:
            reference_image.append([i["url"] for i in s["reference_image"]])

    return prompts, reference_image


if __name__ == "__main__":
    with open("/home/disk2/fanyijie01/banana/test_case/积存金哪个银行费率低.md", "r", encoding="utf-8") as f:
        text = f.read()

    prompts = generate_prompts(text)
    # print(prompts)
    
