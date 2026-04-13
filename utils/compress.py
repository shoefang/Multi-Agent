
"""压缩图片大小"""

from PIL import Image
from io import BytesIO

def compress_image_quality(image, quality=80, save_dir=None):
    """
    压缩图片质量并返回处理后的image对象
    
    参数:
    image: PIL Image对象
    quality: 图片质量 (1-95)
    
    返回:
    PIL Image对象 (压缩后的图片)
    """
    # 如果图片是RGBA或P模式，则转换为RGB
    if image.mode in ('RGBA', 'P'):
        image = image.convert('RGB')
    
    # 创建一个内存中的BytesIO对象来保存压缩后的图片
    buffer = BytesIO()

    if len(save_dir):
        image.save(save_dir, 'JPEG', quality=quality, optimize=True)
        return True
    else:
    # 保存为JPEG格式，设置质量
        image.save(buffer, 'JPEG', quality=quality, optimize=True)
        
        # 从缓冲区创建新的Image对象
        buffer.seek(0)
        compressed_image = Image.open(buffer)
        
        return compressed_image

# 示例用法
if __name__ == "__main__":
    # 打开图片
    input_image = Image.open("input.jpg")
    
    # 压缩图片
    output_image = compress_image_quality(input_image, quality=80)
    
    # 保存结果
    output_image.save("output.jpg")
