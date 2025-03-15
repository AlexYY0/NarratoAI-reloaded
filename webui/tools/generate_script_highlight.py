# 主要事件高光脚本生成
import os
import json
import re
import time
import asyncio
import traceback
import requests
import streamlit as st
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import make_script
from app.config import config
from app.utils.script_generator import ScriptProcessor
from app.utils import utils, video_processor, video_processor_v2, qwenvl_analyzer, gemini_pro_analyzer
from webui.tools.base import create_vision_analyzer, get_batch_files, get_batch_timestamps, chekc_video_config


json_pattern = r'\[.*?\]'


def generate_script_highlight(tr, params):
    """
    生成 主要事件高光 视频脚本
    """
    progress_bar = st.progress(0)
    status_text = st.empty()

    def update_progress(progress: float, message: str = ""):
        progress_bar.progress(progress)
        if message:
            status_text.text(f"{progress}% - {message}")
        else:
            status_text.text(f"进度: {progress}%")

    try:
        with st.spinner("正在生成脚本..."):
            if not params.video_origin_path:
                st.error("请先选择视频文件")
                return

            # ===================因为是基于多模态，所以先直接上传视频文件===================
            # 根据不同的 LLM 提供商处理
            vision_llm_provider = st.session_state.get('vision_llm_providers').lower()
            logger.debug(f"Vision LLM 提供商: {vision_llm_provider}")
            try:
                # ===================初始化视觉分析器===================
                update_progress(10, "正在初始化视觉分析器...")

                # 从配置中获取相关配置
                if vision_llm_provider == 'gemini':
                    vision_api_key = st.session_state.get('vision_gemini_api_key')
                    vision_model = st.session_state.get('vision_gemini_model_name')
                    vision_base_url = st.session_state.get('vision_gemini_base_url')
                else:
                    raise ValueError(f"不支持的视觉分析提供商: {vision_llm_provider}")

                # 创建视觉分析器实例，这里先直接创建，后续再优化
                # analyzer = create_vision_analyzer(
                #     provider=vision_llm_provider,
                #     api_key=vision_api_key,
                #     model=vision_model,
                #     base_url=vision_base_url
                # )
                analyzer = gemini_pro_analyzer.VisionAnalyzer(model_name=vision_model, api_key=vision_api_key)

                update_progress(20, "正在分析视频...")

                gemini_video_file = analyzer.upload_file(st.session_state.get('video_theme', ''), params.video_origin_path, update_progress)

                update_progress(45, "正在匹配解说画面...")

                # 生成解说脚本
                src_script_result = analyzer.analyze_video(gemini_video_file, st.session_state.get('custom_prompt', ''))

                update_progress(60, "格式化解说脚本...")
                # 保存分析结果
                analysis_path = os.path.join(utils.temp_dir(), "frame_analysis.txt")
                with open(analysis_path, 'w', encoding='utf-8') as f:
                    f.write(src_script_result)
                src_script_result = re.findall(json_pattern, src_script_result, re.DOTALL)[0]
                script_result = make_script.parse_frames_by_start_and_end(json.loads(src_script_result))

                # 结果转换为JSON字符串
                script = json.dumps(script_result, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.exception(f"大模型处理过程中发生错误\n{traceback.format_exc()}")
                raise Exception(f"分析失败: {str(e)}")

            if script is None:
                st.error("生成脚本失败，请检查日志")
                st.stop()
            logger.info(f"脚本生成完成")
            if isinstance(script, list):
                st.session_state['video_clip_json'] = script
            elif isinstance(script, str):
                st.session_state['video_clip_json'] = json.loads(script)
            update_progress(80, "脚本生成完成")

        time.sleep(0.1)
        progress_bar.progress(100)
        status_text.text("脚本生成完成！")
        st.success("视频脚本生成成功！")

    except Exception as err:
        st.error(f"生成过程中发生错误: {str(err)}")
        logger.exception(f"生成脚本时发生错误\n{traceback.format_exc()}")
    finally:
        time.sleep(2)
        progress_bar.empty()
        status_text.empty()
