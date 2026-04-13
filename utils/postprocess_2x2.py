"""四宫格方案的后处理模块，包含分割、修复、审核"""


import numpy as np
from PIL import Image
import cv2
from pathlib import Path
import os
import requests


def load_image_from_url(url: str):
    """
    从url下载图片
    """
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    image_bytes = np.asarray(bytearray(response.content), dtype=np.uint8)
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

    return image


def split_2x2(img: Image.Image):
    """
    将单张四宫格切成4张图并返回列表
    """
    w, h = img.size
    hw, hh = w // 2, h // 2

    return [
        img.crop((0, 0, hw, hh)),
        img.crop((hw, 0, w, hh)),
        img.crop((0, hh, hw, h)),
        img.crop((hw, hh, w, h)),
    ]


def split_image_list(image):
    """
    为列表中的每个四宫格进行切分操作
    """
    split_results = []
    parts = split_2x2(image)
    for idx, part in enumerate(parts):
        out_image = remove_black_border(part, idx)
        split_results.append(out_image)
    return split_results
            
    

def remove_black_border(img, idx, border_width=20, black_thresh=30):
    """
    有些切后的图，可能会保留黑边/白边
    这个函数的目的是抹除掉这些黑白色的边界
    """
    img_np = np.array(img)
    cv2_img = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    h, w = cv2_img.shape[:2]
    # border_width = min(max(h, w) // 100, border_width)
    # 2️⃣ 生成边缘区域mask（10px内）
    edge_region = np.zeros((h, w), dtype=bool)
    # if idx == 0:
    #     edge_region[:, -border_width:] = True   # right
    #     edge_region[-border_width:, :] = True   # bottom
    # elif idx == 1:
    #     edge_region[:, :border_width] = True    # left
    #     edge_region[-border_width:, :] = True   # bottom
    # elif idx == 2:
    #     edge_region[:, -border_width:] = True   # right
    #     edge_region[:border_width, :] = True    # top
    # elif idx == 3:
    #     edge_region[:, :border_width] = True    # left
    #     edge_region[:border_width, :] = True    # top

    edge_region[:, -border_width:] = True   # right
    edge_region[-border_width:, :] = True   # bottom
    edge_region[:, :border_width] = True    # left
    edge_region[:border_width, :] = True    # top   

    result = cv2.inpaint(cv2_img, edge_region.astype(np.uint8), 3, cv2.INPAINT_NS)

    img_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
    result_pil = Image.fromarray(img_rgb)


    return result_pil


def detect_case_valid(
    image_input,
    center_tolerance_ratio=0.05,
    thickness_tolerance=3,
    coverage_ratio=0.95
):
    """
    返回：
    False  → 中心没有贯穿线，但其他地方有贯穿线
    True   → 其他情况
    """

    # 如果是 URL
    if isinstance(image_input, str) and image_input.startswith("http"):
        os.environ['http_proxy'] = 'http://agent.baidu.com:8891'
        os.environ['https_proxy'] = 'http://agent.baidu.com:8891'
        image = load_image_from_url(image_input)
        os.environ['http_proxy'] = ''
        os.environ['https_proxy'] = ''


    # 如果是本地路径
    elif isinstance(image_input, str):
        image = cv2.imread(image_input)

    # 如果是PIL.Image
    else:
        image = np.array(image_input)
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    if image is None:
        raise ValueError("无法读取图片")

    h, w = image.shape[:2]

    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    cv2.imwrite("gray.png", gray)

    edges = cv2.Canny(gray, 50, 150)
    edge_mask = (edges > 0).astype(np.uint8)

    center_x = w // 2
    center_y = h // 2

    center_tol_x = int(w * center_tolerance_ratio)
    center_tol_y = int(h * center_tolerance_ratio)

    # ================================
    # 检测任意位置是否存在贯穿水平线
    # ================================
    def has_horizontal_line_in_range(y_start, y_end):
        for y in range(y_start, y_end):
            y1 = max(0, y - thickness_tolerance)
            y2 = min(h, y + thickness_tolerance)

            band = edge_mask[y1:y2, :]
            col_has_edge = np.any(band > 0, axis=0)
            # 这地方有个坑，可能会出现不连续的线，但能覆盖90%以上的（如长虚线），也会被判定为正确，但不影响当前效果
            coverage = np.sum(col_has_edge) / w

            if coverage >= coverage_ratio:
                return True

        return False

    # ================================
    # 检测任意位置是否存在贯穿垂直线
    # ================================
    def has_vertical_line_in_range(x_start, x_end):
        for x in range(x_start, x_end):
            x1 = max(0, x - thickness_tolerance)
            x2 = min(w, x + thickness_tolerance)

            band = edge_mask[:, x1:x2]
            row_has_edge = np.any(band > 0, axis=1)
            coverage = np.sum(row_has_edge) / h
            if coverage >= coverage_ratio:
                return True

        return False

    # 1️⃣ 中心是否有贯穿线
    center_horizontal = has_horizontal_line_in_range(
        center_y - center_tol_y,
        center_y + center_tol_y
    )


    center_vertical = has_vertical_line_in_range(
        center_x - center_tol_x,
        center_x + center_tol_x
    )


    # 2️⃣ 其他位置是否有贯穿线
    other_horizontal = has_horizontal_line_in_range(0, center_y - center_tol_y) or has_horizontal_line_in_range(center_y + center_tol_y, h)
    other_vertical = has_vertical_line_in_range(0, center_x - center_tol_x) or has_vertical_line_in_range(center_x + center_tol_x, w)
    print(center_horizontal, center_vertical, other_horizontal, other_vertical)

    # 只有中心有线
    if center_horizontal and center_vertical and not other_horizontal and not other_vertical:
        return True
    # 哪都没线
    if not center_horizontal and not center_vertical and not other_horizontal and not other_vertical:
        return True

    return False

if __name__ == "__main__":
    # print(detect_case_valid("/home/limonan01/infogram/1-0.png"))
    print(detect_case_valid("/home/limonan01/infogram/0312_res/10万存起来还是买黄金/raw/1.png"))