import os
import re
import json
import traceback
import edge_tts
import asyncio

import requests
from loguru import logger
from typing import List, Iterator
from datetime import datetime
from xml.sax.saxutils import unescape
from edge_tts import submaker, SubMaker
from moviepy.video.tools import subtitles
import time

from app.config import config
from app.utils import utils


def get_all_hailuoai_voices() -> list[str]:
    voices_str = """
温柔学姐:Chinese (Mandarin)_Gentle_Senior
青涩青年音色:male-qn-qingse
精英青年音色:male-qn-jingying
霸道青年音色:male-qn-badao
青年大学生音色:male-qn-daxuesheng
少女音色:female-shaonv
御姐音色:female-yujie
成熟女性音色:female-chengshu
甜美女性音色:female-tianmei
男性主持人:presenter_male
女性主持人:presenter_female
男性有声书1:audiobook_male_1
男性有声书2:audiobook_male_2
女性有声书1:audiobook_female_1
女性有声书2:audiobook_female_2
青涩青年音色-beta:male-qn-qingse-jingpin
精英青年音色-beta:male-qn-jingying-jingpin
霸道青年音色-beta:male-qn-badao-jingpin
青年大学生音色-beta:male-qn-daxuesheng-jingpin
少女音色-beta:female-shaonv-jingpin
御姐音色-beta:female-yujie-jingpin
成熟女性音色-beta:female-chengshu-jingpin
甜美女性音色-beta:female-tianmei-jingpin
聪明男童:clever_boy
可爱男童:cute_boy
萌萌女童:lovely_girl
卡通猪小琪:cartoon_pig
病娇弟弟:bingjiao_didi
俊朗男友:junlang_nanyou
纯真学弟:chunzhen_xuedi
冷淡学长:lengdan_xiongzhang
霸道少爷:badao_shaoye
甜心小玲:tianxin_xiaoling
俏皮萌妹:qiaopi_mengmei
妩媚御姐:wumei_yujie
嗲嗲学妹:diadia_xuemei
淡雅学姐:danya_xuejie
Santa Claus:Santa_Claus 
Grinch:Grinch
Rudolph:Rudolph
Arnold:Arnold
Charming Santa:Charming_Santa
Charming Lady:Charming_Lady
Sweet Girl:Sweet_Girl
Cute Elf:Cute_Elf
Attractive Girl:Attractive_Girl
Serene Woman:Serene_Woman
    """.strip()
    voices = []
    for line in voices_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        voices.append(line)
    voices.sort()
    return voices


def call_tts_stream(text: str, voice_name: str, voice_rate: float, voice_pitch: float) -> Iterator[bytes]:
    tts_url = "https://api.minimax.chat/v1/t2a_v2?GroupId=" + config.hailuoai.get("group_id", "")
    tts_headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'authorization': "Bearer " + config.hailuoai.get("api_key", ""),
    }
    tts_body = json.dumps({
        "model": "speech-01-hd",
        "text": text,
        "stream": True,
        "voice_setting": {
            "voice_id": voice_name,
            "speed": voice_rate,
            "vol": 1.0,
            "pitch": voice_pitch
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1
        }
    })
    response = requests.request("POST", tts_url, stream=True, headers=tts_headers, data=tts_body)
    for chunk in (response.raw):
        if chunk:
            if chunk[:5] == b'data:':
                data = json.loads(chunk[5:])
                if "data" in data and "extra_info" not in data:
                    if "audio" in data["data"]:
                        audio = data["data"]['audio']
                        yield audio


def parse_voice_name(name: str):
    # 青涩青年音色:male-qn-qingse
    # name = name.split(":")[1].strip()
    return name


def is_azure_v2_voice(voice_name: str):
    voice_name = parse_voice_name(voice_name)
    if voice_name.endswith("-V2"):
        return voice_name.replace("-V2", "").strip()
    return ""


def tts(
    text: str, voice_name: str, voice_rate: float, voice_pitch: float, voice_file: str
) -> [SubMaker, None]:
    # if is_azure_v2_voice(voice_name):
    #     return azure_tts_v2(text, voice_name, voice_file)
    return t2a_v2_tts(text, voice_name, voice_rate, voice_pitch, voice_file)


def t2a_v2_tts(
    text: str, voice_name: str, voice_rate: float, voice_pitch: float, voice_file: str
) -> [SubMaker, None]:
    voice_name = parse_voice_name(voice_name)
    text = text.strip()
    for i in range(3):
        try:
            logger.info(f"第 {i+1} 次使用 海螺AI tts 生成音频")

            async def _do() -> tuple[SubMaker, bytes]:
                audio_chunk_iterator  = call_tts_stream(text, voice_name, voice_rate, voice_pitch)
                sub_maker = edge_tts.SubMaker()
                audio_data = bytes()  # 用于存储音频数据
                
                for chunk in audio_chunk_iterator:
                    if chunk is not None and chunk != '\n':
                        decoded_hex = bytes.fromhex(chunk)
                        audio_data +=decoded_hex
                    elif chunk["type"] == "WordBoundary":
                        sub_maker.create_sub(
                            (chunk["offset"], chunk["duration"]), chunk["text"]
                        )
                return sub_maker, audio_data

            # 判断音频文件是否已存在
            if os.path.exists(voice_file):
                logger.info(f"voice file exists, skip tts: {voice_file}")
                continue

            # 获取音频数据和字幕信息
            sub_maker, audio_data = asyncio.run(_do())

            # 验证数据是否有效
            if not sub_maker or not sub_maker.subs or not audio_data:
                logger.warning(f"failed, invalid data generated")
                if i < 2:
                    time.sleep(1)
                continue

            # 数据有效，写入文件
            with open(voice_file, "wb") as file:
                file.write(audio_data)

            logger.info(f"completed, output file: {voice_file}")
            return sub_maker
        except Exception as e:
            logger.error(f"生成音频文件时出错: {str(e)}")
            if i < 2:
                time.sleep(1)
    return None


def t2a_large_v2_tts(text: str, voice_name: str, voice_file: str) -> [SubMaker, None]:
    voice_name = is_azure_v2_voice(voice_name)
    if not voice_name:
        logger.error(f"invalid voice name: {voice_name}")
        raise ValueError(f"invalid voice name: {voice_name}")
    text = text.strip()
    return None


def get_audio_duration(sub_maker: submaker.SubMaker):
    """
    获取音频时长
    """
    if not sub_maker.offset:
        return 0.0
    return sub_maker.offset[-1][1] / 10000000


def tts_multiple(task_id: str, list_script: list, voice_name: str, voice_rate: float, voice_pitch: float, force_regenerate: bool = True):
    """
    根据JSON文件中的多段文本进行TTS转换
    
    :param task_id: 任务ID
    :param list_script: 脚本列表
    :param voice_name: 语音名称
    :param voice_rate: 语音速率
    :param force_regenerate: 是否强制重新生成已存在的音频文件
    :return: 生成的音频文件列表
    """
    voice_name = parse_voice_name(voice_name)
    output_dir = utils.task_dir(task_id)
    audio_files = []
    sub_maker_list = []

    for item in list_script:
        if item['OST'] != 1:
            # 将时间戳中的冒号替换为下划线
            timestamp = item['new_timestamp'].replace(':', '_')
            audio_file = os.path.join(output_dir, f"audio_{timestamp}.mp3")
            
            # 检查文件是否已存在，如存在且不强制重新生成，则跳过
            if os.path.exists(audio_file) and not force_regenerate:
                logger.info(f"音频文件已存在，跳过生成: {audio_file}")
                audio_files.append(audio_file)
                continue

            text = item['narration']

            sub_maker = tts(
                text=text,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_pitch=voice_pitch,
                voice_file=audio_file,
            )

            if sub_maker is None:
                logger.error(f"无法为时间戳 {timestamp} 生成音频; "
                             f"如果您在中国，请使用VPN; "
                             f"或者使用其他 tts 引擎")
                continue

            audio_files.append(audio_file)
            sub_maker_list.append(sub_maker)
            logger.info(f"已生成音频文件: {audio_file}")

    return audio_files, sub_maker_list

if __name__ == '__main__':
    t2a_v2_tts(
        "人工智能不是要替代人类，而是要增强人类的能力。",
        "Chinese (Mandarin)_Gentle_Senior", 1, 1,
        os.path.join(utils.storage_dir("temp", create=True), f"tmp-voice-test.mp3")
    )
