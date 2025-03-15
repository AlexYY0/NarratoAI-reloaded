import json
import math
import os
import re
from typing import List, Dict

from loguru import logger

from app.utils import utils

# 定义需要去掉的特殊字符（可以根据需要扩展）
pattern = r'[,\.,。，、？?；！!《》【】(){}<>"\'\':：\-“”—]'


def time_to_seconds(time_str: str) -> float:
    """
    将时间字符串转换为秒数(带毫秒精度)

    Args:
        time_str: 时间字符串,格式为 "HH:MM:SS,mmm"
                 例如: "00:00:50,100" 表示50.1秒

    Returns:
        float: 转换后的秒数(带毫秒)
    """
    try:
        # 处理毫秒部分
        time_part, ms_part = time_str.split(',')
        hours, minutes, seconds = map(int, time_part.split(':'))
        milliseconds = int(ms_part)

        # 转换为秒
        total_seconds = (hours * 3600) + (minutes * 60) + seconds + (milliseconds / 1000)
        return total_seconds

    except ValueError as e:
        logger.warning(f"时间格式解析错误: {time_str}, error: {e}")
        return 0.0


def format_timestamp(seconds: float) -> str:
    """将秒数转换为 HH:MM:SS,mmm 格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_remainder = seconds % 60
    whole_seconds = int(seconds_remainder)
    milliseconds = int((seconds_remainder - whole_seconds) * 1000)

    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def calculate_duration_by_word_count(word_count: int) -> int:
    """
    计算时间范围的持续时长并估算合适的字数

    Args:
        word_count: 字数
                    基于经验公式: 每0.35秒可以说一个字
                    例如: 10秒可以说约28个字 (10/0.35≈28.57)

        Returns:
            int: 说对应word_count字数需要花费的时间（秒）
    """
    # 根据经验公式计算字数: 每0.5秒一个字
    duration = int(word_count * 0.25)
    return duration


def calculate_duration_by_script(script: str) -> int:
    """
    计算时间范围的持续时长并估算合适的字数

    Args:
        script: 话术脚本
                    基于经验公式: 每0.35秒可以说一个字
                    例如: 10秒可以说约28个字 (10/0.35≈28.57)

        Returns:
            int: 说对应word_count字数需要花费的时间（秒）
    """
    new_script = re.sub(pattern, '', script)  # 使用 re.sub() 替换特殊字符为空字符串
    # 根据经验公式计算字数: 每0.5秒一个字
    duration = int(len(new_script) * 0.25)
    return duration


def parse_frames(sec_frame_content_list: List[Dict]):
    # 计算新的时间戳
    current_time = 0.0  # 当前时间点（秒，包含毫秒）
    frame_content_list: List[Dict] = []
    for src_frame_content in sec_frame_content_list:
        frame_content = dict()
        start_str, middle_str, end_str = src_frame_content["timestamp"].split('-')
        script = src_frame_content["narration"]
        if script:
            frame_content["OST"] = 0
            frame_content["narration"] = script
            new_script = re.sub(pattern, '', script)  # 使用 re.sub() 替换特殊字符为空字符串
            logger.info(f'{script}-->{new_script}')
            duration = calculate_duration_by_word_count(len(new_script))
        else:
            frame_content["OST"] = 1
            frame_content["narration"] = ''
            # 计算当前片段的持续时间
            start_seconds = time_to_seconds(start_str)
            end_seconds = time_to_seconds(end_str)
            duration = end_seconds - start_seconds
        frame_content["picture"] = "None"
        # 设置新的时间戳
        new_start = format_timestamp(current_time)
        new_end = format_timestamp(current_time + duration)
        frame_content['new_timestamp'] = f"{new_start}-{new_end}"
        frame_content_list.append(frame_content)
        # 更新当前时间点
        current_time += duration

        # logger.info(f"时间范围: {frame_content['timestamp']}")
    return frame_content_list


def parse_frames_by_start_or_end(sec_frame_content_list: List[Dict]):
    # 计算新的时间戳
    current_time = 0.0  # 当前时间点（秒，包含毫秒）
    frame_content_list: List[Dict] = []
    for src_frame_content in sec_frame_content_list:
        frame_content = dict()
        start_str, end_str = src_frame_content["timestamp"].split('-')
        script = src_frame_content["narration"]
        if script:
            frame_content["OST"] = 0
            frame_content["narration"] = script
            new_script = re.sub(pattern, '', script)  # 使用 re.sub() 替换特殊字符为空字符串
            duration = calculate_duration_by_word_count(len(new_script))
            if start_str:
                start_seconds = time_to_seconds(start_str)
                frame_content["timestamp"] = f'{start_str}-{format_timestamp(start_seconds + duration)}'
            elif end_str:
                end_seconds = time_to_seconds(end_str)
                frame_content["timestamp"] = f'{format_timestamp(end_seconds - duration)}-{end_str}'
        else:
            frame_content["OST"] = 1
            frame_content["narration"] = ''
            # 计算当前片段的持续时间
            start_seconds = time_to_seconds(start_str)
            end_seconds = time_to_seconds(end_str)
            duration = end_seconds - start_seconds
            frame_content["timestamp"] = f'{start_str}-{end_str}'
        frame_content["picture"] = "None"
        # 设置新的时间戳
        new_start = format_timestamp(current_time)
        new_end = format_timestamp(current_time + duration)
        frame_content['new_timestamp'] = f"{new_start}-{new_end}"
        frame_content_list.append(frame_content)
        # 更新当前时间点
        current_time += duration
    return frame_content_list


def parse_frames_by_start_and_end(sec_frame_content_list: List[Dict]):
    frame_content_list: List[Dict] = []
    for src_frame_content in sec_frame_content_list:
        start_str, end_str = src_frame_content["timestamp"].split('-')
        start_seconds = time_to_seconds(start_str)
        end_seconds = time_to_seconds(end_str)
        script = src_frame_content["narration"]
        # 计算字数-->视频需要截取的长度
        new_script = re.sub(pattern, '', script)  # 使用 re.sub() 替换特殊字符为空字符串
        duration = calculate_duration_by_word_count(len(new_script))

        if start_str and end_str:
            frame_content_start = dict()
            frame_content_start["OST"] = 0
            frame_content_start["narration"] = script
            frame_content_start["picture"] = "None"
            # 此时new_timestamp无所谓，没有用到，后续重新计算
            frame_content_start['new_timestamp'] = "00:00:00,000-00:00:01,000"
            frame_content_start["timestamp"] = f'{start_str}-{format_timestamp(start_seconds + duration)}'
            frame_content_list.append(frame_content_start)

            frame_content_end = dict()
            frame_content_end["OST"] = 0
            frame_content_end["narration"] = script
            frame_content_end["picture"] = "None"
            # 此时new_timestamp无所谓，没有用到，后续重新计算
            frame_content_end['new_timestamp'] = "00:00:00,000-00:00:01,000"
            frame_content_end["timestamp"] = f'{format_timestamp(end_seconds - duration)}-{end_str}'
            frame_content_list.append(frame_content_end)
        elif start_str:
            frame_content_start = dict()
            frame_content_start["OST"] = 0
            frame_content_start["narration"] = script
            frame_content_start["picture"] = "None"
            # 此时new_timestamp无所谓，没有用到，后续重新计算
            frame_content_start['new_timestamp'] = "00:00:00,000-00:00:01,000"
            frame_content_start["timestamp"] = f'{start_str}-{format_timestamp(start_seconds + duration)}'
            frame_content_list.append(frame_content_start)
        elif end_str:
            frame_content_end = dict()
            frame_content_end["OST"] = 0
            frame_content_end["narration"] = script
            frame_content_end["picture"] = "None"
            # 此时new_timestamp无所谓，没有用到，后续重新计算
            frame_content_end['new_timestamp'] = "00:00:00,000-00:00:01,000"
            frame_content_end["timestamp"] = f'{format_timestamp(end_seconds - duration)}-{end_str}'
            frame_content_list.append(frame_content_end)
    return frame_content_list

if __name__ == "__main__":
    # src_script_path = "F:\\我的下载\\寻秦记\\解说数据\\xqj05.json"
    # script_name = "xqj05"
    src_script_path = "F:\\我的下载\\百家讲坛\\王立群\\src\\qsh02.json"
    script_name = "qsh02"
    script_dir = utils.script_dir()
    script_path = os.path.join(script_dir, f"{script_name}.json")
    # 先获取原脚本文件
    # 保存新脚本文件
    with open(src_script_path, 'r', encoding='utf-8') as file:
        src_frame_content_list = json.load(file)

    # 脚本文件处理
    frame_content_list = parse_frames_by_start_or_end(src_frame_content_list)

    # 保存新脚本文件
    with open(script_path, 'w', encoding='utf-8') as file:
        json.dump(frame_content_list, file, ensure_ascii=False, indent=4)
