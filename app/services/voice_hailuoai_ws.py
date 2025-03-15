import functools
import hashlib
import os
import re
import json
import traceback
import urllib
import uuid

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
沉稳高管:226869000163456
新闻女声:226869000163457
舒朗男声:226869000163458
傲娇御姐:226869000163459
不羁青年:226869000163460
嚣张小姐:227505945505984
机械战甲:227505945505985
热心大婶:226869000163462
港普空姐:226869000163463
搞笑大爷:226869000163464
温润男声:226869000163465
温暖闺蜜:226869000163466
播报男声:226869000163467
甜美女声:226869000163468
南方小哥:226869000163469
阅历姐姐:226869000163470
温润青年:226869000163471
温暖少女:226869000163472
花甲奶奶:226869000163473
憨憨萌兽:226869000163474
电台男主播:226869000163475
抒情男声:226869000163476
率真弟弟:226869000163477
真诚青年:226869000163478
温柔学姐:226869000163479
嘴硬竹马:226869000163480
清脆少女:226869000163481
清澈邻家弟弟:226869000163482
软软女孩:226869000163483
    """.strip()
    voices = []
    for line in voices_str.split("\n"):
        line = line.strip()
        if not line:
            continue
        voices.append(line)
    voices.sort()
    return voices


def stream(coroutine_function):
    @functools.wraps(coroutine_function)
    def wrapper(*args, **kwargs):
        coroutine = coroutine_function(*args, **kwargs)
        try:
            while True:
                yield asyncio.run(coroutine.__anext__())
        except StopAsyncIteration:
            pass
    return wrapper


# @stream
async def call_tts_stream(text: str, voice_name: str, voice_rate: float, voice_pitch: float) -> Iterator[bytes]:
    unix = str(int(time.time() * 1000))
    param_str = f"/v1/audio/ws?device_platform=web&app_id=3001&version_code=22201&biz_id=1&uuid={uuid.uuid1()}&lang=zh-Hans&device_id={config.hailuoai.get('device_id', '')}&os_name=Windows&browser_name=edge&device_memory=8&cpu_core_num=12&browser_language=zh-CN&browser_platform=Win32&screen_width=1920&screen_height=1080&unix={unix}"
    yy = hashlib.md5((f"{urllib.parse.quote(param_str, safe='')}_{{}}{hashlib.md5(unix.encode('utf-8')).hexdigest()}ooui").encode("utf-8")).hexdigest()
    tts_url = f"wss://hailuoai.com{param_str}&yy={yy}&token={config.hailuoai.get('token', '')}"
    tts_body = json.dumps({
        "msg_id": str(uuid.uuid1()),
        "payload": {
            "model": "speech-01-hd",
            "text": text,
            "stream": True,
            "voice_setting": {
                "voice_id": voice_name,
                "speed": voice_rate,
                "vol": 2.0,
                "pitch": int(voice_pitch),
                "emotion": "happy",
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1
            },
            "effects": {
                "deepen_lighten": 0,
                "stronger_softer": 0,
                "nasal_crisp": 0,
                "spacious_echo": False,
                "lofi_telephone": False,
                "robotic": False,
                "auditorium_echo": False
            },
            "er_weights": [],
        },
    })
    from websockets import connect
    async with connect(tts_url, max_size=100 * 1024 * 1024) as websocket:
        await websocket.send(tts_body)
        while True:
            message = await websocket.recv()
            if message[2:6] == 'data':
                data = json.loads(message)
                if 'extra_info' in data:
                    yield data
                    break


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
                
                async for chunk in audio_chunk_iterator:
                    if chunk is not None and chunk != '\n':  # 暂时不需要SubMaker，随便给一个值
                        decoded_hex = bytes.fromhex(chunk['data']["audio"])
                        audio_data +=decoded_hex
                        sub_maker.create_sub((0, chunk['extra_info']["audio_length"]), text)
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
    # t2a_v2_tts(
    #     "人工智能不是要替代人类，而是要增强人类的能力。",
    #     "226869000163479", 1, 1,
    #     os.path.join(utils.storage_dir("temp", create=True), f"tmp-voice-test.mp3")
    # )
    t2a_v2_tts(
        "连晋的主公赵穆拿到和氏璧后，沾沾自喜，这既挑起秦赵不和，又铲除了乌家堡，可谓是一箭双雕，身为赵国重臣，为什么要做这么做呢，因为他其实是楚国春申君的私生子，十多年潜伏赵国，以便后续吞并赵国。我们缕一缕，现在的情况是：连晋以为玉是假的，但不知项少龙已掉包。负负得正，赵穆确实拿到了真的和氏璧。",
        "226869000163466", 1.0, 1.0,
        os.path.join(utils.storage_dir("temp", create=True), f"tmp-voice-{uuid.uuid1()}.mp3")
    )
