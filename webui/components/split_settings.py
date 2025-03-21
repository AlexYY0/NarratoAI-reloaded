import glob
import os
import time
import traceback
from pathlib import Path
from uuid import uuid4

import streamlit as st

from app.config import config
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.utils import utils
from webui.utils import file_utils

# 定义临时目录路径
TEMP_SPLIT_DIR = os.path.join("storage", "temp", "split")

# 确保临时目录存在
os.makedirs(TEMP_SPLIT_DIR, exist_ok=True)


def clean_temp_dir():
    """清空临时目录"""
    if os.path.exists(TEMP_SPLIT_DIR):
        for file in os.listdir(TEMP_SPLIT_DIR):
            file_path = os.path.join(TEMP_SPLIT_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                logger.error(f"清理临时文件失败: {str(e)}")


def extract_audio_from_video(video_path, output_audio_path):
    try:
        # 加载视频文件
        video_clip = VideoFileClip(video_path)

        # 提取音频
        audio_clip = video_clip.audio

        # 将音频保存为MP3文件
        audio_clip.write_audiofile(output_audio_path)  # codec：libmp3lame

        # 关闭音频和视频剪辑
        audio_clip.close()
        video_clip.close()

        logger.info("音频已成功提取并保存为 {}", output_audio_path)
    except Exception as e:
        logger.exception("提取{}音频时出错", video_path)


def render_split_settings(tr):
    """Render the split settings section"""
    with st.expander(tr("Video Split"), expanded=False):
        # 视频文件选择
        video_list = [(tr("None"), ""), (tr("Upload Local Files"), "upload_local")]

        # 获取已有视频文件
        for suffix in ["*.mp4", "*.mov", "*.avi", "*.mkv"]:
            video_files = glob.glob(os.path.join(TEMP_SPLIT_DIR, suffix))
            for file in video_files:
                display_name = file.replace(config.root_dir, "")
                video_list.append((display_name, file))

        selected_video_index = st.selectbox(
            tr("Split Video File"),
            index=0,
            options=range(len(video_list)),
            format_func=lambda x: video_list[x][0]
        )

        video_path = video_list[selected_video_index][1]

        if video_path == "upload_local":
            uploaded_file = st.file_uploader(
                tr("Upload Local Files"),
                type=["mp4", "mov", "avi", "flv", "mkv"],
                accept_multiple_files=False,
            )

            if uploaded_file is not None:
                video_path = os.path.join(TEMP_SPLIT_DIR, uploaded_file.name)
                file_name, file_extension = os.path.splitext(uploaded_file.name)

                if os.path.exists(video_path):
                    timestamp = time.strftime("%Y%m%d%H%M%S")
                    file_name_with_timestamp = f"{file_name}_{timestamp}"
                    video_path = os.path.join(TEMP_SPLIT_DIR, file_name_with_timestamp + file_extension)

                with open(video_path, "wb") as f:
                    f.write(uploaded_file.read())
                    st.success(tr("File Uploaded Successfully"))

        # 视频拆分的选项
        if os.path.exists(video_path):
            # 显示视频预览（如果存在）
            player_cols = st.columns(3)
            player_cols[1].video(video_path)
            file_name = Path(video_path).stem
            # 一键转录原声OST
            if st.button(tr("One-Click Transcribe OST"), key=f"transcribe_ost_{file_name}"):
                with st.spinner(tr("Transcribing OST...")):
                    try:
                        task_id = str(uuid4())
                        audio_file = os.path.join(utils.task_dir(task_id), f"{file_name}.mp3")
                        # 方法1：使用moviepy库
                        extract_audio_from_video(video_path, audio_file)
                        # 方法2：使用ffmpeg-python库
                        # 方法3：使用本地的ffmpeg

                        # 显示音频
                        if os.path.exists(audio_file):
                            st.audio(audio_file, format="audio/mp3")
                        else:
                            st.warning(tr("Missing Audio"))

                        file_utils.open_task_folder(config.root_dir, task_id)
                        logger.info(tr("转录原声完成"))
                    except Exception as e:
                        # error_message = str(e)
                        logger.error(traceback.format_exc())
                        st.error(f"{tr('Transcription OST Failed')}: {str(e)}")
        else:
            st.warning(tr("Missing Video"))
