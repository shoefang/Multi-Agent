import os
import requests
import tempfile
import subprocess
import json
import logging
from typing import List, Optional, Tuple
import traceback
from utils.downloads import download_file
from utils.blade_req_texteffect_srt import gen_srt


class VideoProcessor:
    """
    视频处理主类
    """
    def __init__(self,
                 ffmpeg_path: str,
                 ffprobe_path: str,
                 temp_dir: Optional[str] = None,
                 default_resolution: Tuple[int, int] = (720, 1080),  # (1920, 1080) 1080p, (3840, 2160) 4K, (1280, 720) 720p
                 video_codec: str = "libx264", # 标准H.264编码，可选: "libx265" HEVC(更小文件), "prores_ks" 专业编辑
                 audio_codec: str = "aac", # 标准AAC编码，可选: "flac" 无损, "libopus" 高效压缩
                 video_preset: str = "medium", # 编码质量: "slow"(最佳质量), "medium"(平衡), "fast"(快速)
                 video_crf: int = 18,  # 质量系数: 0-51, 0=无损, 18=视觉无损, 23=默认, 28=低质量
                 audio_bitrate: str = "256k",  # 音频比特率: "128k"(一般), "192k"(好), "256k"(很好), "320k"(最佳)
                 temp_audio_prefix: str = "audio",
                 temp_video_prefix: str = "video",
                 temp_bgm_prefix: str = "bgm",
                 temp_processed_prefix: str = "processed",
                 temp_composite_prefix: str = "temp_composite"):
        """
        初始化视频处理器

        Args:
            ffmpeg_path: FFmpeg可执行文件路径
            ffprobe_path: FFprobe可执行文件路径
            temp_dir: 临时文件目录，如果为None则自动创建
            default_resolution: 默认分辨率
            video_codec: 视频编码器
            audio_codec: 音频编码器  
            video_preset: 视频编码预设
            video_crf: 视频质量参数
            audio_bitrate: 音频比特率
            temp_audio_prefix: 临时音频文件前缀
            temp_video_prefix: 临时视频文件前缀
            temp_bgm_prefix: 临时背景音乐文件前缀
            temp_processed_prefix: 临时处理文件前缀
            temp_composite_prefix: 临时合成文件前缀
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.temp_dir = temp_dir or tempfile.mkdtemp()

        self.default_resolution = default_resolution
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.video_preset = video_preset
        self.video_crf = video_crf
        self.audio_bitrate = audio_bitrate
        self.temp_audio_prefix = temp_audio_prefix
        self.temp_video_prefix = temp_video_prefix
        self.temp_bgm_prefix = temp_bgm_prefix
        self.temp_processed_prefix = temp_processed_prefix
        self.temp_composite_prefix = temp_composite_prefix

        # 确保临时目录存在
        os.makedirs(self.temp_dir, exist_ok=True)

        # 设置日志（保持原有print方式）
        self.logger = logging.getLogger(__name__)

        print(f"视频处理器初始化完成")
        print(f"临时文件目录: {self.temp_dir}")
        print(f"FFmpeg路径: {self.ffmpeg_path}")
        print(f"FFprobe路径: {self.ffprobe_path}")

    def run_ffmpeg_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """运行FFmpeg命令"""
        try:
            print(f"执行ffmpeg命令: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            return result
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg命令执行失败: {e}")
            print(f"错误输出: {e.stderr}")
            print(f"ffmpeg报错：{e}")
            raise
    
    

    def create_composite_video_no_audio(self,
                                    video_paths: List[str],
                                    output_path: str,
                                    resolution: Tuple[int, int] = None) -> str:
        """
        合并所有没有音频的视频片段

        Args:
            video_paths: 视频文件路径列表
            output_path: 输出文件路径
            resolution: 输出视频分辨率，如果为None则使用默认分辨率

        Returns:
            合并后的视频文件路径
        """
        if resolution is None:
            resolution = self.default_resolution
            
        try:
            # 如果只有一个视频，直接处理
            if len(video_paths) == 1:
                cmd = [
                    self.ffmpeg_path,
                    '-i', video_paths[0],
                    '-vf',
                    f'scale={resolution[0]}:{resolution[1]}:force_original_aspect_ratio=decrease:flags=lanczos,'
                    f'pad={resolution[0]}:{resolution[1]}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                    '-c:v', self.video_codec,
                    '-preset', self.video_preset,
                    '-crf', str(self.video_crf),
                    '-r', '30',  # 统一帧率
                    '-an',  # 禁用音频
                    '-movflags', '+faststart',
                    '-y',
                    output_path
                ]
                print(f"执行单视频处理命令: {' '.join(cmd)}")
                self.run_ffmpeg_command(cmd)
                
            else:
                # 分步处理：先预处理单个视频，再拼接
                temp_files = []
                try:
                    # 第一步：分别处理每个视频的缩放（统一编码参数）
                    for i, video_path in enumerate(video_paths):
                        temp_output = f"{output_path}.temp_{i}.mp4"
                        temp_files.append(temp_output)
                        
                        # 获取原始视频信息
                        video_info = self.get_video_info(video_path)
                        original_fps = video_info.get('fps', 30)
                        
                        scale_cmd = [
                            self.ffmpeg_path,
                            '-i', video_path,
                            '-vf',
                            f'scale={resolution[0]}:{resolution[1]}:force_original_aspect_ratio=decrease:flags=lanczos,'
                            f'pad={resolution[0]}:{resolution[1]}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                            '-c:v', self.video_codec,
                            '-preset', 'fast',  # 预处理用fast加快速度
                            '-crf', str(self.video_crf),
                            '-r', '30',  # 统一输出帧率
                            '-g', '60',  # 统一GOP大小
                            '-an',  # 禁用音频
                            '-movflags', '+faststart',
                            '-threads', '2',  # 限制线程数，减少资源占用
                            '-avoid_negative_ts', 'make_zero',  # 处理负时间戳
                            '-fflags', '+genpts',  # 生成正确的时间戳
                            '-y',
                            temp_output
                        ]
                        
                        print(f"预处理视频 {i+1}/{len(video_paths)}: {os.path.basename(video_path)}")
                        self.run_ffmpeg_command(scale_cmd)
                    
                    # 第二步：使用filter_complex拼接（避免时间戳问题）
                    inputs = []
                    filter_parts = []
                    
                    for i, temp_file in enumerate(temp_files):
                        inputs.extend(['-i', temp_file])
                        filter_parts.append(f"[{i}:v]")
                    
                    # 构建concat滤镜
                    filter_complex = "".join(filter_parts) + f"concat=n={len(temp_files)}:v=1:a=0[outv]"
                    
                    concat_cmd = [
                        self.ffmpeg_path
                    ] + inputs + [
                        '-filter_complex', filter_complex,
                        '-map', '[outv]',
                        '-c:v', self.video_codec,
                        '-preset', 'fast',
                        '-crf', str(self.video_crf),
                        '-r', '30',  # 统一输出帧率
                        '-an',  # 确保没有音频
                        '-movflags', '+faststart',
                        '-avoid_negative_ts', 'make_zero',  # 处理负时间戳
                        '-fflags', '+genpts',  # 生成正确的时间戳
                        '-max_muxing_queue_size', '1024',  # 防止muxing队列溢出
                        '-y',
                        output_path
                    ]
                    
                    print("开始拼接视频...")
                    self.run_ffmpeg_command(concat_cmd)
                    
                finally:
                    # 清理临时文件
                    self._cleanup_temp_files(temp_files)
                    
            # 验证输出视频时长
            try:
                output_duration = self.get_duration(output_path)
                input_durations = sum([self.get_duration(path) for path in video_paths])
                print(f"输入视频总时长: {input_durations:.2f}s, 输出视频时长: {output_duration:.2f}s")

                if abs(output_duration - input_durations) > 1.0:  # 允许1秒误差
                    print(f"警告: 输出视频时长与输入总时长差异较大: {abs(output_duration - input_durations):.2f}s")
            except Exception as e:
                print(f"警告: 无法验证视频时长: {e}")

            return output_path

        except Exception as e:
            print(f"创建无音频合成视频失败: {e}")
            raise

    def get_video_info(self, file_path: str) -> dict:
        """
        获取视频详细信息
        """
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=r_frame_rate,codec_name,width,height',
                '-of', 'json',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            info = json.loads(result.stdout)
            
            if 'streams' in info and len(info['streams']) > 0:
                stream = info['streams'][0]
                fps_str = stream.get('r_frame_rate', '30/1')
                if '/' in fps_str:
                    num, den = fps_str.split('/')
                    fps = float(num) / float(den)
                else:
                    fps = float(fps_str)
                
                return {
                    'fps': fps,
                    'codec': stream.get('codec_name', ''),
                    'width': int(stream.get('width', 0)),
                    'height': int(stream.get('height', 0))
                }
            
            return {'fps': 30, 'codec': 'unknown', 'width': 0, 'height': 0}
        
        except Exception as e:
            print(f"警告: 获取视频信息失败: {e}")
            return {'fps': 30, 'codec': 'unknown', 'width': 0, 'height': 0}

    def _cleanup_temp_files(self, file_paths: List[str]):
        """清理临时文件"""
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"已清理临时文件: {file_path}")
            except Exception as e:
                print(f"警告: 清理临时文件失败 {file_path}: {e}")

    # 添加一个静音音轨，替换原有音轨
    def remove_audio(self, video_path):
        """
        为视频添加精确时长的静音音轨（修复版）
        关键改进：确保静音音轨与视频时长完全一致
        """
        output_filename = f"{self.temp_processed_prefix}_no_audio_{os.path.basename(video_path)}"
        output_path = os.path.join(self.temp_dir, output_filename)   
        duration = self.get_duration(video_path)
        
        command = [
            self.ffmpeg_path, "-y",
            '-i', video_path,                    # 输入视频
            '-f', 'lavfi',
            '-i', f'anullsrc=duration={duration}:sample_rate=44100',  # 精确时长的静音
            '-c:v', 'copy',                      # 复制视频
            '-c:a', self.audio_codec,            # 编码音频
            '-map', '0:v:0',                     # 选择第一个输入的视频流
            '-map', '1:a:0',                     # 选择第二个输入的音频流
            '-shortest',                         # 以较短的流为准（应该相等）
            output_path
        ]
        
        self.run_ffmpeg_command(command)
        
        # 验证处理后的时长是否一致
        original_duration = self.get_duration(video_path)
        processed_duration = self.get_duration(output_path)
        
        if abs(original_duration - processed_duration) > 0.05:  # 50ms误差内
            print(f"警告：处理前后时长不一致。原始：{original_duration}s，处理后：{processed_duration}s")
        
        print(f"视频已移除/替换音频，保存到：{output_path}")
        return output_path

    def get_media_info(self, file_path: str) -> dict:
        """获取媒体文件信息"""
        try:
            cmd = [
                self.ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except Exception as e:
            print(f"获取媒体信息失败 {file_path}: {e}")
            raise

    def get_video_resolution(self, file_path: str) -> tuple:
        """获取视频分辨率

        Args:
            file_path: 视频文件路径

        Returns:
            tuple: (width, height) 分辨率元组

        Raises:
            Exception: 当获取媒体信息失败或找不到视频流时
        """
        try:
            media_info = self.get_media_info(file_path)

            # 查找视频流
            for stream in media_info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = stream.get('width')
                    height = stream.get('height')

                    if width and height:
                        return width, height

            raise Exception(f"在文件 {file_path} 中未找到视频流信息")

        except Exception as e:
            print(f"获取视频分辨率失败 {file_path}: {e}")
            raise

    def get_duration(self, file_path: str) -> float:
        """获取媒体文件时长"""
        if file_path is None or file_path == "":
            raise Exception(f"@get_duration, file_path={file_path} not exist!")

        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise Exception(f"@get_duration, file_path={file_path} does not exist!")
        
        # 检查文件大小是否合理（大于1KB）
        file_size = os.path.getsize(file_path)
        if file_size < 1024:
            raise Exception(f"@get_duration, file_path={file_path} is too small ({file_size} bytes), likely corrupted")
        
        info = self.get_media_info(file_path)
        
        # 检查duration字段是否存在
        if 'format' not in info or 'duration' not in info['format']:
            raise Exception(f"@get_duration, Cannot get duration from file: {file_path}")
        
        return float(info['format']['duration'])

    def process_audio_match_audio(self, video_path: str, audio_path: str, 
                                save_video_path: str = None, cutting_time: float = 0.0) -> str:
        """
        以音频时长为准处理音视频，可选择删除视频前几秒
        音频短：视频正常播放，音频结束后静音
        音频长：视频减速播放以匹配音频时长
        
        Args:
            video_path: 视频文件路径
            audio_path: 音频文件路径
            save_video_path: 输出视频路径，如果为None则自动生成
            cutting_time: 要删除的视频前部秒数，默认为1秒
            
        Returns:
            处理后的视频路径
        """
        try:
            # 获取视频和音频时长
            video_duration = self.get_duration(video_path)
            audio_duration = self.get_duration(audio_path)
            
            print(f"以音频时长为准处理: 原视频={video_duration:.2f}s, 音频={audio_duration:.2f}s, 删除前{cutting_time:.1f}秒")
            
            if not save_video_path:
                output_filename = f"{self.temp_processed_prefix}_match_audio_{os.path.basename(video_path)}"
                output_path = os.path.join(self.temp_dir, output_filename)
            else:
                output_path = save_video_path
            
            # 如果需要剪切视频前部
            if cutting_time > 0 and video_duration > cutting_time:
                # 步骤1: 删除视频前cutting_time秒
                temp_video_filename = f"{self.temp_processed_prefix}_cut_{os.path.basename(video_path)}"
                temp_video_path = os.path.join(self.temp_dir, temp_video_filename)
                
                # 使用精确剪切（从第cutting_time秒开始）
                cut_cmd = [
                    self.ffmpeg_path,
                    '-i', video_path,
                    '-ss', str(cutting_time),  # 从第cutting_time秒开始
                    '-c', 'copy',  # 复制编码，提高速度
                    '-avoid_negative_ts', 'make_zero',
                    '-y',
                    temp_video_path
                ]
                
                print(f"剪切视频前{cutting_time:.1f}秒...")
                self.run_ffmpeg_command(cut_cmd)
                
                # 验证剪切结果
                try:
                    # 获取剪切后的视频时长
                    cut_video_duration = self.get_duration(temp_video_path)
                    print(f"剪切后视频时长: {cut_video_duration:.2f}s")
                    
                    # 检查剪切后的时长是否合理（应该在原始时长减去剪切时间附近）
                    expected_duration = video_duration - cutting_time
                    if abs(cut_video_duration - expected_duration) > 1.0:  # 允许1秒误差
                        print(f"警告: 剪切后时长({cut_video_duration:.2f}s)与预期({expected_duration:.2f}s)差异较大，使用原始视频")
                        actual_video_path = video_path
                        actual_video_duration = video_duration
                    else:
                        # 剪切成功，使用剪切后的视频
                        actual_video_path = temp_video_path
                        actual_video_duration = cut_video_duration
                        
                except Exception as cut_error:
                    print(f"剪切操作验证失败: {cut_error}，回退到使用原始视频")
                    actual_video_path = video_path
                    actual_video_duration = video_duration
            else:
                # 不需要剪切或无法剪切，使用原视频
                if cutting_time > 0 and video_duration <= cutting_time:
                    print(f"警告: 视频时长({video_duration:.2f}s)小于等于要剪切的时间({cutting_time:.1f}s)，跳过剪切")
                
                actual_video_path = video_path
                actual_video_duration = video_duration
            
            # 步骤2: 比较实际视频时长和音频时长，按原逻辑处理
            if audio_duration <= actual_video_duration:
                # 音频比视频短或相等：视频正常播放，音频结束后静音
                print("音频短于视频，视频正常播放，音频后接静音")
                cmd = [
                    self.ffmpeg_path,
                    '-i', actual_video_path,
                    '-i', audio_path,
                    '-filter_complex',
                    f'[1:a]apad=pad_dur={actual_video_duration - audio_duration}[padded_audio]',
                    '-map', '0:v',
                    '-map', '[padded_audio]',
                    '-c:v', self.video_codec,
                    '-c:a', self.audio_codec,
                    '-preset', 'fast',
                    '-shortest',
                    '-y',
                    output_path
                ]
            else:
                # 音频比视频长：视频减速播放
                speed_factor = actual_video_duration / audio_duration
                print(f"音频长于视频，视频减速播放，速度因子: {speed_factor:.3f}")

                cmd = [
                    self.ffmpeg_path,
                    '-i', actual_video_path,
                    '-i', audio_path,
                    '-filter_complex',
                    f'[0:v]setpts={1 / speed_factor}*PTS[slow_video]',
                    '-map', '[slow_video]',
                    '-map', '1:a',
                    '-c:v', self.video_codec,
                    '-c:a', self.audio_codec,
                    '-preset', 'fast',
                    '-shortest',
                    '-y',
                    output_path
                ]

            self.run_ffmpeg_command(cmd)
            
            # 清理临时剪切文件
            if cutting_time > 0 and video_duration > cutting_time:
                try:
                    os.remove(temp_video_path)
                    print(f"已清理临时剪切文件: {temp_video_path}")
                except Exception as e:
                    print(f"警告: 清理临时剪切文件失败: {e}")
            
            # 验证输出时长
            try:
                final_duration = self.get_duration(output_path)
                print(f"最终视频时长: {final_duration:.2f}s")
            except Exception as e:
                print(f"警告: 无法获取输出视频时长: {e}")
            
            print(f"视频和音频合并后，保存在 {output_path}")
            return output_path

        except Exception as e:
            print(f"以音频时长处理失败: {e}")
            raise


    # 所有视频片段有音频时，合并各个视频片段
    def create_composite_video(self,
                          video_paths: List[str],
                          output_path: str,
                          resolution: Tuple[int, int] = None) -> str:
        """
        合并所有视频片段（严格统一帧率版）
        1. 独立预处理：将每个VFR视频彻底转换为标准CFR
        2. 简单拼接：使用concat demuxer合并处理后的中间文件
        """
        if resolution is None:
            resolution = self.default_resolution

        try:
            print("开始合成视频（严格统一帧率流程）...")

            # 创建临时工作目录
            import tempfile
            import shutil
            temp_dir = tempfile.mkdtemp(prefix="ffmpeg_cfr_")
            print(f"临时工作目录: {temp_dir}")

            # 定义统一的目标参数
            target_fps = 30  # 统一的目标帧率，也可根据你的需求改为25
            cfr_videos = []  # 保存转换后的CFR视频路径
            list_file_path = os.path.join(temp_dir, "concat_list.txt")

            try:
                # 第一步：独立、严格地将每个视频转换为CFR
                for idx, input_video in enumerate(video_paths):
                    print(f"\n[{idx+1}/{len(video_paths)}] 处理: {os.path.basename(input_video)}")

                    # 获取原始时长，用于验证
                    original_duration = self.get_duration(input_video)
                    print(f"  原始时长: {original_duration:.3f} 秒")

                    # 输出中间文件路径
                    cfr_video = os.path.join(temp_dir, f"cfr_{idx:03d}.mp4")
                    cfr_videos.append(cfr_video)

                    # **核心转换命令**
                    # 此命令强制FFmpeg忽略输入流的所有时间特性，按照我们设定的严格参数输出
                    convert_cmd = [
                        self.ffmpeg_path, '-y',
                        '-i', input_video,                 # 输入源
                        # === 视频流处理 ===
                        '-vf', f'fps={target_fps}',        # **强制**设置输出帧率
                        '-vsync', 'cfr',                   # 恒定帧率模式
                        '-r', str(target_fps),             # 再次指定输出帧率
                        '-c:v', self.video_codec,
                        '-preset', 'fast',
                        '-crf', str(self.video_crf),
                        '-video_track_timescale', '90000', # 统一时间基准（重要！）
                        # === 音频流处理 ===
                        '-c:a', self.audio_codec,          # 音频也重新编码，确保同步
                        '-b:a', self.audio_bitrate,
                        '-ar', '44100',                    # 统一采样率
                        '-ac', '2',                        # 统一双声道
                        # === 全局控制 ===
                        '-fflags', '+genpts',              # 强制生成新的PTS（关键！）
                        '-avoid_negative_ts', 'make_zero', # 从0开始计时
                        '-shortest',                       # 以音视频中短的为准
                        cfr_video
                    ]
                    print(f"  执行CFR转换...")
                    self.run_ffmpeg_command(convert_cmd)

                    # 验证转换后视频的时长
                    cfr_duration = self.get_duration(cfr_video)
                    print(f"  转换后时长: {cfr_duration:.3f} 秒")
                    if abs(cfr_duration - original_duration) > 0.1:
                        print(f"  ⚠️  注意：转换前后时长有轻微差异 ({cfr_duration - original_duration:+.3f}s)，这在VFR转CFR时可能发生。")

                # 第二步：将所有CFR视频进行缩放和填充至目标分辨率
                print(f"\n第二步：统一缩放所有视频至 {resolution[0]}x{resolution[1]}")
                scaled_videos = []
                for idx, cfr_video in enumerate(cfr_videos):
                    scaled_video = os.path.join(temp_dir, f"scaled_{idx:03d}.mp4")
                    scaled_videos.append(scaled_video)

                    scale_cmd = [
                        self.ffmpeg_path, '-y',
                        '-i', cfr_video,
                        '-vf',
                        f'scale={resolution[0]}:{resolution[1]}:force_original_aspect_ratio=decrease:flags=lanczos,'
                        f'pad={resolution[0]}:{resolution[1]}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                        '-c:v', self.video_codec,
                        '-preset', 'fast',
                        '-crf', str(self.video_crf), # 可以适度提高1-2，因已是二次编码
                        '-c:a', 'copy',              # 视频已处理，音频直接复制
                        scaled_video
                    ]
                    self.run_ffmpeg_command(scale_cmd)

                # 第三步：创建文件列表，进行最终拼接
                print(f"\n第三步：拼接 {len(scaled_videos)} 个处理后的视频")
                with open(list_file_path, 'w', encoding='utf-8') as f:
                    for video in scaled_videos:
                        f.write(f"file '{os.path.abspath(video)}'\n")

                # 使用concat demuxer进行拼接，它最适用于处理编码参数一致的CFR文件
                concat_cmd = [
                    self.ffmpeg_path, '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', list_file_path,
                    '-c', 'copy',           # 流直接复制，无二次编码，速度快且无损
                    '-movflags', '+faststart',
                    output_path
                ]
                self.run_ffmpeg_command(concat_cmd)

                # 最终验证
                print(f"\n第四步：最终验证")
                total_input_duration = sum([self.get_duration(path) for path in video_paths])
                final_duration = self.get_duration(output_path)
                print(f"  输入视频总时长: {total_input_duration:.3f}s")
                print(f"  输出视频总时长: {final_duration:.3f}s")
                print(f"  时长差异: {final_duration - total_input_duration:+.3f}s")
                if abs(final_duration - total_input_duration) < 0.5:
                    print("  ✅ 成功！时长在可接受误差范围内。")
                else:
                    print(f"  ❌ 警告：最终时长仍有明显差异。")

            finally:
                # 清理临时目录
                if os.path.exists(temp_dir):
                    print(f"\n清理临时目录: {temp_dir}")
                    shutil.rmtree(temp_dir)

            return output_path

        except Exception as e:
            print(f"创建合成视频失败: {e}")
            raise

    def has_audio(self, file_path: str) -> bool:
        """检查文件是否包含音频流"""
        info = self.get_media_info(file_path)
        for stream in info['streams']:
            if stream['codec_type'] == 'audio':
                return True
        return False
    
    def get_audio(self,video_path, save_path):
        cmd = [
                    self.ffmpeg_path, 
                    '-i', video_path,
                    '-vn',        # 流直接复制，无二次编码，速度快且无损s
                    save_path
                ]
        self.run_ffmpeg_command(cmd)


    # 视频片段合并
    def process(self,
                slices: dict,
                output_path: str = "final_video.mp4",
                bgm_url: Optional[str] = None,
                audio_strategy: str = "",
                bgm_volume: float = None,
                resolution: Tuple[int, int] = None,
                auto_cleanup: bool = True,
                cutting_time: float = 0.0) -> str:
        """
        主方法：创建带有音频的合成视频

        Args:
            slices: 分镜数据
            output_path: 输出文件路径
            bgm_url: 背景音乐URL
            audio_strategy: 音频处理策略
            bgm_volume: 背景音乐音量
            resolution: 输出视频分辨率，如果为None则使用默认分辨率
            auto_cleanup: 是否自动清理临时文件
            
        Returns:
            最终视频文件路径
        """

        print("开始合成视频啦！！！！")
        if resolution is None:
            resolution = self.default_resolution
            
        try:
            # 验证输入参数
            audio_urls, video_urls, plan_durations = [], [], []
            for i, shot in enumerate(slices['shots'], 1):
                if shot['line']=='' or shot["need_lip_driven"]:
                    audio_urls.append(None)
                    
                else:
                    audio_urls.append(shot["speech"])
                video_urls.append(shot["video"])
                plan_durations.append(self.get_duration(shot["video"]))

            # 1. 准备所有音频、视频文件
            audio_paths = []
            for i, url in enumerate(audio_urls):
                if url is None:
                    audio_paths.append(None)
                else:
                    try:
                        print("开始下载音频文件...")
                        save_file_path = os.path.join("./", f"{self.temp_audio_prefix}_{i}.mp3")
                        if self.temp_dir:
                            save_file_path = os.path.join(self.temp_dir, f"{self.temp_audio_prefix}_{i}.mp3")
                        path = download_file(url, save_file_path)
                        audio_paths.append(path)
                    except:
                        audio_paths.append(url)

            video_paths = video_urls

            # 2. 处理每个音视频对
            print("处理音视频对...")
            processed_video_paths = []

            for i, shot in enumerate(slices['shots']):
                print(f"处理第 {i + 1} 个片段...")
                video_path = video_paths[i]
                audio_path = audio_paths[i]
                if shot["line"]=='':
                    processed_path = self.remove_audio(video_path)
                elif shot['need_lip_driven']:
                    processed_path = video_path
                else:
                    processed_path = self.process_audio_match_audio(video_path, audio_path, cutting_time=cutting_time)
                
                processed_duration = self.get_duration(processed_path)
                original_duration = self.get_duration(video_path)
                print(f"  片段{i+1}: 原始={original_duration:.3f}s, 处理后={processed_duration:.3f}s, "
                    f"差异={processed_duration - original_duration:+.3f}s")
        
                processed_video_paths.append(processed_path)

            # 3. 创建合成视频，按照第一个视频片段设置分辨率
            print("创建合成视频...")
            resolution = self.get_video_resolution(processed_video_paths[0])
            self.create_composite_video(processed_video_paths, output_path, resolution)

            print(f"视频合成完成: {output_path}")
            return output_path

        except Exception as e:
            print(f"视频合成失败: {e}")
            raise
        finally:
            if auto_cleanup:
                self.cleanup()

    def cleanup(self):
        """清理临时文件"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
            print("临时文件已清理")
        except Exception as e:
            print(f"警告: 清理临时文件失败: {e}")

    def process_audio_match_audio2(self, video_path: str, audio_path: str, save_video_path: str = None) -> str:
        """
        以音频时长为准处理音视频
        音频短：视频正常播放，音频结束后静音
        音频长：视频减速播放以匹配音频时长
        """
        try:
            video_duration = self.get_duration(video_path)
            audio_duration = self.get_duration(audio_path)

            print(f"处理音视频匹配: 视频={video_duration:.2f}s, 音频={audio_duration:.2f}s")

            if not save_video_path:
                output_filename = f"{self.temp_processed_prefix}_match_audio_{os.path.basename(video_path)}"
                output_path = os.path.join(self.temp_dir, output_filename)
            else:
                output_path = save_video_path

            if audio_duration <= video_duration:
                # 逻辑：视频原速，音频补静音到视频的时长
                print("音频较短：补齐静音")
                filter_str = f"[1:a]apad=whole_dur={video_duration}[a]"
                v_map = "0:v" # 视频直接用原流
            else:
                # 逻辑：视频减速，使视频时长等于音频时长
                # 计算 PTS 缩放倍数：目标时长 / 当前时长
                speed_factor = audio_duration / video_duration
                print(f"音频较长：视频减速 {speed_factor:.3f}x")
                filter_str = f"[0:v]setpts={speed_factor}*PTS[v]"
                v_map = "[v]"

            cmd = [
                self.ffmpeg_path,
                '-y',
                '-loglevel', 'quiet',  # 不打印处理过程
                '-i', video_path,
                '-i', audio_path,
                '-filter_complex', filter_str,
                '-map', v_map,
                '-map', '[a]' if audio_duration <= video_duration else '1:a',
                '-c:v', self.video_codec,
                '-c:a', self.audio_codec,
                '-ar', '44100',  # 确保音频兼容性
                '-preset', 'fast',
                output_path
            ]

            self.run_ffmpeg_command(cmd)
            print(f"合并完成: {output_path}")
            return output_path

        except Exception as e:
            print(f"音视频匹配失败: {e}")
            raise

    def change_video_speed(self,
                        input_path: str,
                        output_path: str,
                        speed_factor: float,
                        audio_method: str = "atempo") -> str:
        """
        视频变速处理（同时处理视频和音频）

        Args:
            input_path: 输入视频文件路径(变速前视频路径)
            output_path: 输出视频文件路径(变速后视频路径)
            speed_factor: 速度倍率
            audio_method: 音频变速方法，"atempo", "rubberband", "asetpts"

        Returns:
            处理后的视频文件路径
        """
        try:
            if not os.path.exists(input_path):
                raise Exception(f"@change_video_speed, input_path={input_path} not exist!")
            
            if speed_factor > 1.3:
                print(f"warn!!! speed_factor={speed_factor} > 1.3")

            print(f"开始视频变速: {input_path} -> {output_path}")
            print(f"速度倍率: {speed_factor}, 音频方法: {audio_method}")

            # 检查视频是否有音频
            has_audio = self.has_audio(input_path)

            # 使用setpts进行视频变速
            if has_audio:
                # 同时处理视频和音频
                filter_complex = f"[0:v]setpts=PTS/{speed_factor}[v];[0:a]{self._get_audio_speed_filter(audio_method, speed_factor)}[a]"
                cmd = [
                    self.ffmpeg_path,
                    '-i', input_path,
                    '-filter_complex', filter_complex,
                    '-map', '[v]',
                    '-map', '[a]',
                    '-c:v', self.video_codec,
                    '-preset', self.video_preset,
                    '-crf', str(self.video_crf),
                    '-c:a', self.audio_codec,
                    '-b:a', self.audio_bitrate,
                    '-movflags', '+faststart',
                    '-y',
                    output_path
                ]
            else:
                print("变速视频没有音频")
                cmd = [
                    self.ffmpeg_path,
                    '-i', input_path,
                    '-vf', f"setpts=PTS/{speed_factor}",
                    '-c:v', self.video_codec,
                    '-preset', self.video_preset,
                    '-crf', str(self.video_crf),
                    '-an',  # 没有音频流
                    '-movflags', '+faststart',
                    '-y',
                    output_path
                ]

            self.run_ffmpeg_command(cmd)

            # 验证输出
            if not os.path.exists(output_path):
                raise RuntimeError(f"视频变速失败，输出文件未生成: {output_path}")

            original_duration = self.get_duration(input_path)
            new_duration = self.get_duration(output_path)
            expected_duration = original_duration / speed_factor

            print(f"视频变速完成: 原时长={original_duration:.2f}s, "
                  f"新时长={new_duration:.2f}s, 预期={expected_duration:.2f}s")

            return output_path

        except Exception as e:
            print(f"视频变速失败: {e}")
            raise

    def _get_audio_speed_filter(self, method: str, speed_factor: float) -> str:
        """根据方法获取音频变速滤镜字符串"""
        if method == "atempo":
            if speed_factor < 0.5 or speed_factor > 2.0:
                # 需要多个atempo串联
                factors = []
                remaining = speed_factor
                while remaining < 0.5 or remaining > 2.0:
                    if remaining < 0.5:
                        factors.append(0.5)
                        remaining /= 0.5
                    else:
                        factors.append(2.0)
                        remaining /= 2.0
                factors.append(remaining)
                return ",".join([f"atempo={f:.3f}" for f in factors])
            else:
                return f"atempo={speed_factor:.3f}"
        elif method == "asetpts":
            return f"asetpts=PTS/{speed_factor:.3f}"
        elif method == "rubberband":
            return f"rubberband=tempo={speed_factor:.3f}"
        else:
            raise ValueError(f"不支持的音频变速方法: {method}")

    # 按照帧裁剪，精确但是慢(误差0.01内)
    def trim_video_hybrid(self, video_path: str, start_time: float, duration: float, output_path: str = None) -> str:
        """
        混合方法：先快速定位，再精确裁剪
        """
        try:
            self.logger.info(f"混合模式裁剪: {video_path}")
            
            # 构建输出路径
            dir_name = os.path.dirname(video_path)
            file_name = os.path.basename(video_path)
            name, ext = os.path.splitext(file_name)
            if output_path is None:
                output_filename = f"{name}_混合裁剪_{start_time:.2f}s-{duration:.2f}s{ext}"
                output_path = os.path.join(dir_name, output_filename)
            
            # 混合方法命令：-ss 放在 -i 前面可以快速定位
            command = [
                str(self.ffmpeg_path),  # 确保ffmpeg路径也是字符串
                '-y',
                '-ss', str(start_time),
                '-i', str(video_path),  # 确保视频路径是字符串
                '-t', str(duration),
                '-c:v', 'libx264',
                '-c:a', 'aac',
                '-avoid_negative_ts', 'make_zero',
                '-preset', 'medium',
                '-crf', '23',
                '-movflags', '+faststart',
                str(output_path)  # 确保输出路径也是字符串
            ]
            
            self.run_ffmpeg_command(command)
            self.logger.info(f"混合裁剪完成: {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"混合裁剪失败: {e}")
            raise


    def get_subtitle_info(self,video_path,slices_path,audio_path):
        
        with open(os.path.join(slices_path), "r") as f:
            slices = json.loads(f.read())
        subtitle_content=''
        for shot in slices['shots']:
            subtitle_content = subtitle_content+shot['line']

        
        if not os.path.exists(audio_path):
            self.get_audio(video_path,audio_path)
        return audio_path, subtitle_content
    

    

    def video_add_srt(self, video_input_path, srt_input_path, video_output_path, font_file_path=None, font_name="Noto Sans SC"):
        """
        视频添加字幕，适配 Linux 环境，支持指定字体文件路径。
        此函数使用 FFmpeg 的 subtitles 滤镜并将 SRT 硬烧录(Hardsub)进视频中。

        Args:
            video_input_path: 视频输入路径
            srt_input_path:   SRT 字幕文件路径
            video_output_path: 视频输出路径
            font_file_path:   字体文件的绝对路径 (例如: "/usr/share/fonts/NotoSansSC-Regular.ttf")
                            如果提供此参数，脚本会将该文件所在目录加入 FFmpeg 搜索路径 (:fontsdir)。
            font_name:        字体名称 (Family Name)。
                            注意：即使提供了文件路径，这里仍需填入字体内部名称。
                            可以使用 `fc-scan 字体文件路径` 命令在 Linux 下查看 "fullname" 或 "family"。
                            例如: "Noto Sans SC", "Microsoft YaHei", "Arial".
        """

        # 1. 参数验证
        if not os.path.exists(video_input_path):
            raise FileNotFoundError(f"视频文件不存在: {video_input_path}")
        if not os.path.exists(srt_input_path):
            raise FileNotFoundError(f"字幕文件不存在: {srt_input_path}")
        
        # 验证字体文件是否存在
        fonts_dir_option = ""
        if font_file_path:
            if not os.path.exists(font_file_path):
                raise FileNotFoundError(f"字体文件不存在: {font_file_path}")
            font_dir = os.path.dirname(os.path.abspath(font_file_path))
            # 告诉 FFmpeg 在除了系统目录外，还要去这个目录找字体
            fonts_dir_option = f":fontsdir='{font_dir}'"
            print(f"使用临时字体目录: {font_dir}")

        # 2. 检查输出目录
        output_dir = os.path.dirname(video_output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            # 3. 构建滤镜字符串
            # ---------------------------------------------------------------------
            # [样式修改指南]
            # force_style 里的参数决定了字幕的外观。
            # 格式说明：Key=Value，多个参数用逗号隔开。
            # ---------------------------------------------------------------------
            subtitle_filter = (
                f"subtitles='{srt_input_path}':"
                f"charenc=UTF-8{fonts_dir_option}:"  # 关键修改：加入字体目录
                "force_style="
                f"'FontName={font_name},"       # 字体名称
                "FontSize=15,"                  # [字号]: 修改数字调整大小 (例如: 18, 24, 32)
                "PrimaryColour=&HFFFFFF&,"      # [主体颜色]: 字体颜色 (格式 &HBBGGRR&，详见下方说明)
                                                # &HFFFFFF& = 白色, &H00FFFF& = 黄色, &H0000FF& = 红色
                "OutlineColour=&H000000&,"      # [描边颜色]: 黑色 (&H000000&)
                "BackColour=&H80000000&,"       # [背景/阴影颜色]: &H80000000& (带透明度的黑色)
                "BorderStyle=1,"                # [边框样式]: 1=普通描边+阴影, 3=不透明矩形背景框
                "Outline=1,"                    # [描边宽度]: 数字越大边框越粗 (例如: 0, 1, 2, 3)
                "Shadow=0.5,"                   # [阴影深度]: 数字越大阴影越明显 (例如: 0, 1, 2)
                "Alignment=2,"                  # [对齐方式]: 小键盘布局。2=底部居中, 1=左下, 3=右下, 5=正中
                "MarginV=30'"                   # [垂直边距]: 字幕距离视频底部的距离 (像素 px)
            )

            cmd = [
                self.ffmpeg_path,
                "-i", video_input_path,
                "-vf", subtitle_filter,
                "-c:v", "libx264",
                "-crf", str(self.video_crf),
                "-preset", self.video_preset,
                "-c:a", self.audio_codec,
                "-b:a", self.audio_bitrate,
                "-y",
                video_output_path
            ]

            print(f"正在执行 FFmpeg，使用字体名: {font_name}")
            if font_file_path:
                print(f"加载外部字体文件: {font_file_path}")

            # 5. 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )

            if result.returncode != 0:
                print("FFmpeg 执行出错 stderr:")
                print(result.stderr)
                if "Fontconfig error" in result.stderr or "Impossible to find a matching font" in result.stderr:
                    print(f"!!! 错误提示: FFmpeg 找不到字体 '{font_name}'。")
                    if font_file_path:
                        print(f"请确认 '{font_name}' 是否是文件 '{os.path.basename(font_file_path)}' 的正确内部名称。")
                raise RuntimeError("FFmpeg 执行失败")

            print("字幕添加完成!")
            return True

        except Exception as e:
            print(f"字幕添加失败，异常: {e}")
            traceback.print_exc()
            return False
        

    def gen_srt_video(self,video_path,slices_path):
        with open(os.path.join(slices_path), "r") as f:
            slices = json.loads(f.read())
        data_dir = os.path.dirname(video_path)
        audio_path = f"{data_dir}/audio.wav"

        print("分离音频")
        audio_path, subtitle_content = self.get_subtitle_info(video_path,slices_path,audio_path)

        print("生成字幕文件")
        res = gen_srt(audio_path, subtitle_content)
        srt_path =f"{data_dir}/subtitle.srt"
        download_file(res["audio_fragment_srt_url"],srt_path)

        font_path = "/home/data/1029_ad_video2/utils/FZLanTYJW_Da.TTF"
        font_name = "FZLanTingYuanS-EB-GB"
        if os.path.exists(f"{data_dir}/{slices['goods_name']}.mp4"):
            video_input_path = f"{data_dir}/{slices['goods_name']}.mp4"
        elif os.path.exists(f"{data_dir}/video_with_bgm.mp4"):
            video_input_path = f"{data_dir}/video_with_bgm.mp4"
        else:
            video_input_path = f".mp4"
        video_output_path= f"{data_dir}/final.mp4"

        print("为视频加入字幕")
        self.video_add_srt(video_input_path, srt_path, video_output_path, font_path, font_name)


    def video_add_audio_simple(self, video_path, audio_path, output_video_path):
        """
        输入：video必须是没有音频的
        输出：1、若音频时长大于视频，则只取前面一段。
             2、若音频时长小于视频，则循环播放音频
        """
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', video_path,
                '-stream_loop', '-1',  # 无限循环BGM
                '-i', audio_path,
                '-map', '0:v',
                '-map', '1:a',
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-shortest',  # 以视频时长为准
                '-y',
                output_video_path
            ]
            subprocess.run(cmd, check=True)
            print(f"无声视频添加音频成功，保存路径:{output_video_path}")
            return True 
        except Exception as e:
            print(f"音频添加失败，异常: {e}, 详细报错:{traceback.print_exc()}")
            return False

if __name__ == "__main__":
    # 使用示例
    FFMPEG_PATH = "/home/work/zhonglong/ad_video/tools/ffmpeg-6.0-amd64-static/ffmpeg"
    FFPROBE_PATH = "/home/work/zhonglong/ad_video/tools/ffmpeg-6.0-amd64-static/ffprobe"
    
    # 创建视频处理器实例（现在可以直接传入配置参数）
    video_processor = VideoProcessor(
        ffmpeg_path=FFMPEG_PATH,
        ffprobe_path=FFPROBE_PATH,
        temp_dir="/home/data/1029_ad_video2/ad_video_test/datasets/outputs/koubo_output/0/temp",
        default_resolution=(720, 1280)
    )

    # 添加字幕
    data_dir = "/home/data/1029_ad_video2/ad_video_test/datasets/zhongcao_output"
    fail_list =[]
    for data in os.listdir(data_dir):
        try:

            video_path = f"{data_dir}/{data}/final_video_no_bgm.mp4"
            slices_path = f"{data_dir}/{data}/slices.json"
            
            video_processor.gen_srt_video(video_path,slices_path)
        except:
            fail_list.append(data)
    with(open("/home/data/1029_ad_video2/ad_video_test/datasets/fail_list.txt","w")) as f:
        f.write(str(fail_list))


   

    
#/home/data/python_env_bos/python_env/bin/pythonx