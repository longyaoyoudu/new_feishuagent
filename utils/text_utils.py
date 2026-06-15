import re
import json
from typing import Any
from .logger import logger


def remove_think_content(text: str) -> str:
    """
    移除文本中的 <think></think> 标签及其内容
    支持多种变体格式，确保彻底过滤思考内容
    
    Args:
        text: 原始文本
        
    Returns:
        过滤后的文本
    """
    if not text:
        return text
    
    original_length = len(text)
    result = text
    
    think_patterns = [
        r'<think>.*?</think>',
        r'<Think>.*?</Think>',
        r'<THINK>.*?</THINK>',
        r'<\s*think\s*>.*?<\s*/\s*think\s*>',
        r'<\s*Think\s*>.*?<\s*/\s*Think\s*>',
        r'<\s*THINK\s*>.*?<\s*/\s*THINK\s*>',
    ]
    
    for pattern in think_patterns:
        result = re.sub(pattern, '', result, flags=re.DOTALL | re.IGNORECASE)
    
    while re.search(r'<think[^>]*>.*?</think>', result, flags=re.DOTALL | re.IGNORECASE):
        result = re.sub(r'<think[^>]*>.*?</think>', '', result, flags=re.DOTALL | re.IGNORECASE)
    
    result = result.strip()
    
    if len(result) != original_length:
        logger.debug(f"已移除思考内容: 原长度 {original_length}，过滤后长度 {len(result)}")
    
    return result


def extract_json_from_text(text: str) -> str:
    """
    从文本中提取 JSON 内容
    
    支持以下格式：
    - 纯 JSON 字符串
    - 包含在 ```json ... ``` 的代码块
    - 包含在 ``` ... ``` 的代码块
    - JSON 前后有其他文字
    
    Args:
        text: 包含 JSON 的文本
        
    Returns:
        提取的 JSON 字符串，如果没有找到则返回原始文本
    """
    if not text:
        return text
    
    json_match = None
    
    json_patterns = [
        r'```\s*json\s*\n(.*?)\n```',
        r'```\s*JSON\s*\n(.*?)\n```',
        r'```\s*Json\s*\n(.*?)\n```',
        r'```\s*\n(.*?)\n```',
    ]
    
    for pattern in json_patterns:
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            json_match = match.group(1).strip()
            logger.debug(f"从代码块中提取到 JSON: {json_match[:100]}...")
            return json_match
    
    json_start = text.find('{')
    json_end = text.rfind('}')
    
    if json_start != -1 and json_end != -1 and json_end > json_start:
        json_match = text[json_start:json_end + 1].strip()
        logger.debug(f"从文本中提取到 JSON 片段: {json_match[:100]}...")
        return json_match
    
    return text.strip()


def clean_model_output(text: str) -> str:
    """
    清理模型输出，移除思考内容等不必要的部分
    
    Args:
        text: 原始模型输出
        
    Returns:
        清理后的文本
    """
    result = remove_think_content(text)
    
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = re.sub(r' +', ' ', result)
    
    lines = result.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    result = '\n'.join(cleaned_lines)
    
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')
    
    return result.strip()


def safe_json_loads(text: str) -> Any:
    """
    安全地解析 JSON，支持多种格式
    
    Args:
        text: 可能包含 JSON 的文本
        
    Returns:
        解析后的 JSON 对象，如果解析失败则抛出异常
    """
    if not text:
        raise ValueError("输入文本为空")
    
    json_str = extract_json_from_text(text)
    
    try:
        result = json.loads(json_str)
        logger.debug(f"成功解析 JSON: {str(result)[:100]}...")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {str(e)}")
        logger.error(f"原始文本: {text[:200]}...")
        logger.error(f"提取的 JSON: {json_str[:200]}...")
        raise
