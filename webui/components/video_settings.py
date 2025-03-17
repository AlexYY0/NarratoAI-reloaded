import streamlit as st
from app.models.schema import VideoClipParams, VideoAspect, VideoConcatMode, VideoTransitionMode


def render_video_panel(tr):
    """渲染视频配置面板"""
    with st.container(border=True):
        st.write(tr("Video Settings"))
        params = VideoClipParams()
        render_video_config(tr, params)


def render_video_config(tr, params):
    """渲染视频配置"""
    # 视频拼接模式
    video_concat_modes = [
        (tr("Sequential"), "sequential"),
        (tr("Random"), "random"),
    ]
    selected_index = st.selectbox(
        tr("Video Concat Mode"),
        index=1,
        options=range(
            len(video_concat_modes)
        ),  # Use the index as the internal option value
        format_func=lambda x: video_concat_modes[x][
            0
        ],  # The label is displayed to the user
    )
    params.video_concat_mode = VideoConcatMode(
        video_concat_modes[selected_index][1]
    )
    st.session_state['video_concat_mode'] = params.video_concat_mode.value
    # 视频转场模式
    video_transition_modes = [
        (tr("None"), VideoTransitionMode.none.value),
        (tr("Shuffle"), VideoTransitionMode.shuffle.value),
        (tr("FadeIn"), VideoTransitionMode.fade_in.value),
        (tr("FadeOut"), VideoTransitionMode.fade_out.value),
        (tr("SlideIn"), VideoTransitionMode.slide_in.value),
        (tr("SlideOut"), VideoTransitionMode.slide_out.value),
    ]
    selected_index = st.selectbox(
        tr("Video Transition Mode"),
        options=range(len(video_transition_modes)),
        format_func=lambda x: video_transition_modes[x][0],
        index=0,
    )
    params.video_transition_mode = VideoTransitionMode(
        video_transition_modes[selected_index][1]
    )
    st.session_state['video_transition_mode'] = params.video_transition_mode.value
    # 视频比例
    video_aspect_ratios = [
        (tr("Portrait"), VideoAspect.portrait.value),
        (tr("Landscape"), VideoAspect.landscape.value),
    ]
    selected_index = st.selectbox(
        tr("Video Ratio"),
        options=range(len(video_aspect_ratios)),
        format_func=lambda x: video_aspect_ratios[x][0],
    )
    params.video_aspect = VideoAspect(video_aspect_ratios[selected_index][1])
    st.session_state['video_aspect'] = params.video_aspect.value
    # 视频片段最大时长
    params.video_clip_duration = st.selectbox(
        tr("Clip Duration"), options=[2, 3, 4, 5, 6, 7, 8, 9, 10], index=1
    )
    st.session_state['video_clip_duration'] = params.video_clip_duration
    # 同时生成视频数量
    params.video_count = st.selectbox(
        tr("Number of Videos Generated Simultaneously"),
        options=[1, 2, 3, 4, 5],
        index=0,
    )
    st.session_state['video_count'] = params.video_count

    # 视频画质
    video_qualities = [
        ("4K (2160p)", "2160p"),
        ("2K (1440p)", "1440p"),
        ("Full HD (1080p)", "1080p"),
        ("HD (720p)", "720p"),
        ("SD (480p)", "480p"),
    ]
    quality_index = st.selectbox(
        tr("Video Quality"),
        options=range(len(video_qualities)),
        format_func=lambda x: video_qualities[x][0],
        index=2  # 默认选择 1080p
    )
    st.session_state['video_quality'] = video_qualities[quality_index][1]

    # 原声音量
    params.original_volume = st.slider(
        tr("Original Volume"),
        min_value=0.0,
        max_value=1.0,
        value=0.7,
        step=0.01,
        help=tr("Adjust the volume of the original audio")
    )
    st.session_state['original_volume'] = params.original_volume


def get_video_params():
    """获取视频参数"""
    return {
        'video_aspect': st.session_state.get('video_aspect', VideoAspect.portrait.value),
        'video_quality': st.session_state.get('video_quality', '1080p'),
        'original_volume': st.session_state.get('original_volume', 0.7)
    }
