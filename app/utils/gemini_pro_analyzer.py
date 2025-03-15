import traceback
from typing import Union, TextIO

from google import genai
from google.api_core import exceptions
from google.api_core.exceptions import PermissionDenied, ResourceExhausted, InvalidArgument, AlreadyExists, FailedPrecondition
from google.generativeai.types import BlockedPromptException, BrokenResponseError, IncompleteIterationError
from googleapiclient.errors import ResumableUploadError
from loguru import logger
from tenacity import retry, stop_after_attempt, RetryError, retry_if_exception_type, wait_exponential


def handle_exception(err):
    if isinstance(err, PermissionDenied):
        raise Exception("403 用户没有权限访问该资源")
    elif isinstance(err, ResourceExhausted):
        raise Exception("429 您的配额已用尽。请稍后重试。请考虑设置自动重试来处理这些错误")
    elif isinstance(err, InvalidArgument):
        raise Exception("400 参数无效。例如，文件过大，超出了载荷大小限制。另一个事件提供了无效的 API 密钥。")
    elif isinstance(err, AlreadyExists):
        raise Exception("409 已存在具有相同 ID 的已调参模型。对新模型进行调参时，请指定唯一的模型 ID。")
    elif isinstance(err, RetryError):
        raise Exception("使用不支持 gRPC 的代理时可能会引起此错误。请尝试将 REST 传输与 genai.configure(..., transport=rest) 搭配使用。")
    elif isinstance(err, BlockedPromptException):
        raise Exception("400 出于安全原因，该提示已被屏蔽。")
    elif isinstance(err, BrokenResponseError):
        raise Exception("500 流式传输响应已损坏。在访问需要完整响应的内容（例如聊天记录）时引发。查看堆栈轨迹中提供的错误详情。")
    elif isinstance(err, IncompleteIterationError):
        raise Exception("500 访问需要完整 API 响应但流式响应尚未完全迭代的内容时引发。对响应对象调用 resolve() 以使用迭代器。")
    elif isinstance(err, ConnectionError):
        raise Exception("网络连接错误, 请检查您的网络连接(建议使用 NarratoAI 官方提供的 url)")
    else:
        raise Exception(f"大模型请求失败, 下面是具体报错信息: \n\n{traceback.format_exc()}")


class VisionAnalyzer:
    """视觉分析器类"""

    def __init__(self, model_name: str = "gemini-1.5-flash", api_key: str = None):
        """初始化视觉分析器"""
        if not api_key:
            raise ValueError("必须提供API密钥")

        self.model_name = model_name
        self.api_key = api_key

        # 初始化配置
        self._configure_client()

    def _configure_client(self):
        """配置API客户端"""
        self.client = genai.Client(api_key=self.api_key)
        # 开放 Gemini 模型安全设置
        from google.genai import types
        from google.genai.types import HarmCategory, HarmBlockThreshold
        self.config = types.GenerateContentConfig(
            safety_settings=[
                types.SafetySetting(
                    category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=HarmBlockThreshold.BLOCK_NONE
                ),
                types.SafetySetting(
                    category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=HarmBlockThreshold.BLOCK_NONE
                ),
                types.SafetySetting(
                    category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=HarmBlockThreshold.BLOCK_NONE
                ),
                types.SafetySetting(
                    category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=HarmBlockThreshold.BLOCK_NONE
                )
            ]
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(exceptions.ResourceExhausted)
    )
    async def _generate_content_with_retry(self, prompt, batch):
        """使用重试机制的内部方法来调用 generate_content_async"""
        try:
            return await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[prompt, *batch]
            )
        except exceptions.ResourceExhausted as e:
            print(f"API配额限制: {str(e)}")
            raise RetryError("API调用失败")

    def _generate_response_video(self, prompt: str, video_file: Union[str, TextIO]) -> str:
        """
        多模态能力大模型
        """
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, video_file],
                config=self.config
            )
            return response.text
        except Exception as err:
            return handle_exception(err)

    def upload_file(self, video_name: str, video_path: str, progress_callback=None):
        """上传文件"""
        logger.debug(f"视频名称: {video_name}")
        try:
            if progress_callback:
                progress_callback(25, "上传视频至 Google cloud")
            gemini_video_file = self.client.files.upload(file=video_path)
            # gemini_video_file = self.client.files.get(name="files/592n4627z47k")
            logger.debug(f"视频 {gemini_video_file.name} 上传至 Google cloud 成功, 开始解析...")
            while gemini_video_file.state.name == "PROCESSING":
                gemini_video_file = self.client.files.get(name=gemini_video_file.name)
                if progress_callback:
                    progress_callback(35, "上传成功, 开始解析")  # 更新进度为35%
            if gemini_video_file.state.name == "FAILED":
                raise ValueError(gemini_video_file.state.name)
            elif gemini_video_file.state.name == "ACTIVE":
                if progress_callback:
                    progress_callback(40, "解析完成, 开始匹配解说画面...")  # 更新进度为40%
                logger.debug("解析完成, 开始匹配解说画面...")
            return gemini_video_file
        except ResumableUploadError as err:
            logger.error(f"上传视频至 Google cloud 失败, 用户的位置信息不支持用于该API; \n{traceback.format_exc()}")
            return False
        except FailedPrecondition as err:
            logger.error(f"400 用户位置不支持 Google API 使用。\n{traceback.format_exc()}")
            return False

    def analyze_video(self, gemini_video_file, narrate_json):
        """视频分析"""
        try:
            logger.info('使用模型{}分析视频', self.model_name)
            print(self._get_default_prompt(narrate_json))
            response = self._generate_response_video(prompt=self._get_default_prompt(narrate_json), video_file=gemini_video_file)
            logger.success("视频匹配解说画面成功")
            logger.debug(response)
            print(type(response))
            return response
        except Exception as err:
            return handle_exception(err)

    def _get_default_prompt(self, narrate_json) -> str:
        return """
**背景：**
现在有一个【视频主要事件描述】的JSON数组，数据如下：
```json
%s
```
数组每个索引的对象结构如下：
    - "narration"：主要事件的画面语言描述

**角色：**
你是一名视频分析专家，需要根据输入【视频主要事件描述】和视频里人物的说话、动作、表情，找出视频里与【视频主要事件描述】匹配的视频片段。

**要求：**
1. 【视频主要事件描述】和匹配的视频片段 要求准确无误，即使重新匹配，结果的误差也不超过60秒
2. 结果输出为JSON数组格式，每个索引对象包含字段：
    - "narration"：【视频主要事件描述】
    - "timestamp"：与【视频主要事件描述】匹配的视频片段。找出视频片段与【视频主要事件描述】开头匹配度最高的时间戳，格式为"HH:MM:SS,FFF"，例如"00:00:03,000"；找出视频片段与【视频主要事件描述】结尾匹配度最高的时间戳，格式为"HH:MM:SS,FFF"，例如"00:00:13,345"
3. 请以严格的 JSON 格式返回数据，不要包含任何注释、标记或其他字符。数据应符合 JSON 语法，可以被 json.loads() 函数直接解 析， 不要添加 ```json 或其他标记。

**请按照以下步骤思考并解答这道题：**
1. 遍历【视频主要事件描述】JSON数组
2. 根据每个索引对象的"narration"字段，找出匹配的视频片段，找出视频片段与【视频主要事件描述】开头匹配度最高的时间戳和结尾匹配度最高的时间戳，组成格式为"HH:MM:SS,FFF-HH:MM:SS,FFF"，例如"00:00:03,000-00:00:13,345"
3. 暂存第2步匹配的结尾时间戳【last_timestamp】，下一个索引对象的视频片段匹配从【last_timestamp】开始

**限制：**
1. 匹配时跳过视频开头的片头曲、视频结束的片尾曲、视频中间的过场动画

**输入示例：**
```json
[
    {
        "narration": "一队军人护送一批科学家到达了目的地"
    },
    {
        "narration": "他死死的攥者护身符，一直不停的祈祷"
    }
]
```

**输出示例：**
```json
[
    {
        "timestamp": "00:00:01,000-00:00:08,123",
        "narration": "一队军人护送一批科学家到达了目的地"
    },
    {
        "timestamp": "00:00:10,555-00:00:13,345",
        "narration": "他死死的攥者护身符，一直不停的祈祷"
    }
]
```
""" % (narrate_json)