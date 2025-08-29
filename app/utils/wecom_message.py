#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
企业微信消息处理工具函数
提供流式消息构造、图片处理等功能
"""

import json
import base64
import hashlib
import random
import string
import time
import requests
import logging
from typing import Dict, Any, Tuple, Optional
from Crypto.Cipher import AES

from app.config import settings

logger = logging.getLogger(__name__)


def get_agent_id_from_aibot(aibotid: str) -> Optional[str]:
    """
    根据 aibotid 获取对应的 Dify agentid
    
    Args:
        aibotid: 企业微信智能机器人ID
        
    Returns:
        对应的 Dify agentid，如果未找到则返回 None
    """
    try:
        import json
        mapping = json.loads(settings.WECOM_AIBOT_AGENT_MAPPING)
        agent_id = mapping.get(aibotid)
        if not agent_id:
            logger.warning(f"未找到 aibotid {aibotid} 对应的 agentid，将使用默认配置")
        return agent_id
    except json.JSONDecodeError as e:
        logger.error(f"解析 WECOM_AIBOT_AGENT_MAPPING 配置失败: {e}")
        return None
    except Exception as e:
        logger.error(f"获取 agentid 时发生错误: {e}")
        return None


def generate_random_string(length: int = 10) -> str:
    """生成随机字符串作为流ID"""
    letters = string.ascii_letters + string.digits
    return ''.join(random.choice(letters) for _ in range(length))


def make_text_stream(stream_id: str, content: str, finish: bool = False) -> str:
    """
    构造文本流式消息
    
    Args:
        stream_id: 流ID
        content: 文本内容
        finish: 是否结束
        
    Returns:
        JSON格式的流式消息字符串
    """
    plain = {
        "msgtype": "stream",
        "stream": {
            "id": stream_id,
            "finish": finish,
            "content": content
        }
    }
    return json.dumps(plain, ensure_ascii=False)


def make_image_stream(stream_id: str, image_data: bytes, finish: bool = False) -> str:
    """
    构造图片流式消息
    
    Args:
        stream_id: 流ID
        image_data: 图片二进制数据
        finish: 是否结束
        
    Returns:
        JSON格式的流式消息字符串
    """
    image_md5 = hashlib.md5(image_data).hexdigest()
    image_base64 = base64.b64encode(image_data).decode('utf-8')

    plain = {
        "msgtype": "stream",
        "stream": {
            "id": stream_id,
            "finish": finish,
            "msg_item": [
                {
                    "msgtype": "image",
                    "image": {
                        "base64": image_base64,
                        "md5": image_md5
                    }
                }
            ]
        }
    }
    return json.dumps(plain, ensure_ascii=False)


def make_mixed_stream(stream_id: str, items: list, finish: bool = False) -> str:
    """
    构造混合内容流式消息（文本+图片）
    
    Args:
        stream_id: 流ID
        items: 消息项列表，每项包含 msgtype 和对应的内容
        finish: 是否结束
        
    Returns:
        JSON格式的流式消息字符串
    """
    plain = {
        "msgtype": "stream",
        "stream": {
            "id": stream_id,
            "finish": finish,
            "msg_item": items
        }
    }
    return json.dumps(plain, ensure_ascii=False)


def make_template_card(card_data: Dict[str, Any]) -> str:
    """
    构造模板卡片消息
    
    Args:
        card_data: 模板卡片的内容数据
        
    Returns:
        JSON格式的模板卡片消息字符串
    """
    plain = {
        "msgtype": "template_card",
        "template_card": card_data
    }
    return json.dumps(plain, ensure_ascii=False)


def convert_image_url_to_proxy(original_url: str) -> str:
    """
    将原始的腾讯云COS图片URL转换为代理服务器格式
    
    Args:
        original_url: 原始图片URL，格式如：https://ww-aibot-img-1258476243.cos.ap-guangzhou.myqcloud.com/xxxxxxxxxx
        
    Returns:
        转换后的代理URL，格式如：http://{ip}?path=xxxxxxxxxx
    """
    if not settings.IMAGE_PROXY_IP:
        logger.warning("未配置IMAGE_PROXY_IP，将使用原始URL")
        return original_url
    
    try:
        # 提取URL中的文件路径部分
        # 原始URL格式：https://ww-aibot-img-1258476243.cos.ap-guangzhou.myqcloud.com/xxxxxxxxxx
        if "cos.ap-guangzhou.myqcloud.com/" in original_url:
            # 提取域名后的路径部分
            path_part = original_url.split("cos.ap-guangzhou.myqcloud.com/", 1)[1]
            # 构造代理URL
            proxy_url = f"http://{settings.IMAGE_PROXY_IP}/cos-image?path={path_part}"
            logger.info(f"URL转换: {original_url} -> {proxy_url}")
            return proxy_url
        else:
            logger.warning(f"URL格式不匹配，无法转换: {original_url}")
            return original_url
            
    except Exception as e:
        logger.error(f"URL转换失败: {e}")
        return original_url


def make_welcome_template_card(agent_name: str = "AI助手") -> str:
    """
    构造欢迎模板卡片
    
    Args:
        agent_name: 智能助手的名称
        
    Returns:
        JSON格式的欢迎卡片消息字符串
    """
    card_data = {
        "card_type": "text_notice",
        "source": {
            "icon_url": "https://wework.qpic.cn/wwpic/252813_jOfDHtcISzuodLa_1629280209/0",
            "desc": agent_name,
            "desc_color": 1
        },
        "main_title": {
            "title": f"欢迎使用{agent_name}",
            "desc": "我是您的智能助手，可以帮您解答问题、提供信息和协助工作"
        },
        "emphasis_content": {
            "title": "在线",
            "desc": "服务状态"
        },
        "horizontal_content_list": [
            {
                "keyname": "功能",
                "value": "智能问答、知识查询、工作协助"
            },
            {
                "keyname": "支持",
                "value": "文本、图片、混合消息"
            }
        ],
        "jump_list": [
            {
                "type": 3,
                "title": "了解功能",
                "question": "你有哪些功能？"
            },
            {
                "type": 3,
                "title": "使用帮助",
                "question": "如何使用你？"
            }
        ]
    }
    
    return make_template_card(card_data)


def process_encrypted_image(image_url: str, aes_key_base64: str) -> Tuple[bool, bytes | str]:
    """
    下载并解密加密图片
    
    Args:
        image_url: 加密图片的URL
        aes_key_base64: Base64编码的AES密钥(与回调加解密相同)
        
    Returns:
        tuple: (status: bool, data: bytes/str) 
               status为True时data是解密后的图片数据，
               status为False时data是错误信息
    """
    try:
        # 1. 转换为代理URL并下载加密图片
        proxy_url = convert_image_url_to_proxy(image_url)
        logger.info(f"开始下载加密图片: {proxy_url}")
        response = requests.get(proxy_url, timeout=15)
        response.raise_for_status()
        encrypted_data = response.content
        logger.info(f"图片下载成功，大小: {len(encrypted_data)} 字节")
        
        # 2. 准备AES密钥和IV
        if not aes_key_base64:
            raise ValueError("AES密钥不能为空")
            
        # Base64解码密钥 (自动处理填充)
        aes_key = base64.b64decode(aes_key_base64 + "=" * (-len(aes_key_base64) % 4))
        if len(aes_key) != 32:
            raise ValueError("无效的AES密钥长度: 应为32字节")
            
        iv = aes_key[:16]  # 初始向量为密钥前16字节
        
        # 3. 解密图片数据
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_data = cipher.decrypt(encrypted_data)
        
        # 4. 去除PKCS#7填充 (Python 3兼容写法)
        pad_len = decrypted_data[-1]  # 直接获取最后一个字节的整数值
        if pad_len > 32:  # AES-256块大小为32字节
            raise ValueError("无效的填充长度 (大于32字节)")
            
        decrypted_data = decrypted_data[:-pad_len]
        logger.info(f"图片解密成功，解密后大小: {len(decrypted_data)} 字节")
        
        return True, decrypted_data
        
    except requests.exceptions.RequestException as e:
        error_msg = f"图片下载失败: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
        
    except ValueError as e:
        error_msg = f"参数错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f"图片处理异常: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def parse_markdown_images(text: str) -> Tuple[str, list]:
    """
    解析Markdown中的图片链接
    
    Args:
        text: 包含Markdown图片语法的文本
        
    Returns:
        tuple: (纯文本内容, 图片URL列表)
    """
    import re
    
    # 匹配Markdown图片语法: ![alt](url)
    image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    images = []
    
    # 提取图片信息
    for match in re.finditer(image_pattern, text):
        alt_text = match.group(1)
        image_url = match.group(2)
        images.append({
            'alt': alt_text,
            'url': image_url,
            'match': match.group(0)
        })
    
    # 移除图片语法，保留纯文本
    clean_text = re.sub(image_pattern, '', text).strip()
    
    return clean_text, images


async def download_image(url: str) -> Tuple[bool, bytes | str]:
    """
    异步下载图片
    
    Args:
        url: 图片URL
        
    Returns:
        tuple: (success: bool, data: bytes/error_msg: str)
    """
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            # 检查是否为图片类型
            content_type = response.headers.get('content-type', '').lower()
            if not content_type.startswith('image/'):
                return False, f"URL 不是图片类型: {content_type}"
                
            logger.info(f"图片下载成功: {url}, 大小: {len(response.content)} 字节")
            return True, response.content
            
    except Exception as e:
        error_msg = f"下载图片失败 {url}: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


class StreamMessageCache:
    """流式消息缓存管理器"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._processed_msgids: set = set()  # 消息去重
        self._cleanup_interval = 3600  # 1小时清理一次
        self._last_cleanup = time.time()
    
    def create_stream(self, stream_id: str, user_query: str) -> None:
        """创建新的流式消息缓存"""
        self._cache[stream_id] = {
            'user_query': user_query,
            'created_time': time.time(),
            'text_parts': [],
            'images': [],
            'is_finished': False,
            'conversation_id': None
        }
        self._cleanup_old_streams()
    
    def add_text_part(self, stream_id: str, text: str) -> None:
        """添加文本部分"""
        if stream_id in self._cache:
            self._cache[stream_id]['text_parts'].append(text)
    
    def add_image(self, stream_id: str, image_data: bytes) -> None:
        """添加图片"""
        if stream_id in self._cache:
            self._cache[stream_id]['images'].append(image_data)
    
    def set_conversation_id(self, stream_id: str, conversation_id: str) -> None:
        """设置对话ID"""
        if stream_id in self._cache:
            self._cache[stream_id]['conversation_id'] = conversation_id
    
    def mark_finished(self, stream_id: str) -> None:
        """标记流式消息完成"""
        if stream_id in self._cache:
            self._cache[stream_id]['is_finished'] = True
    
    def get_stream_data(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """获取流式消息数据"""
        return self._cache.get(stream_id)
    
    def get_current_content(self, stream_id: str) -> str:
        """获取当前累积的文本内容"""
        if stream_id not in self._cache:
            return ""
        return ''.join(self._cache[stream_id]['text_parts'])
    
    def is_finished(self, stream_id: str) -> bool:
        """检查流式消息是否完成"""
        if stream_id not in self._cache:
            return True
        return self._cache[stream_id]['is_finished']
    
    def remove_stream(self, stream_id: str) -> None:
        """移除流式消息缓存"""
        self._cache.pop(stream_id, None)
    
    def is_message_processed(self, msgid: str) -> bool:
        """检查消息是否已处理（去重）"""
        return msgid in self._processed_msgids
    
    def mark_message_processed(self, msgid: str) -> None:
        """标记消息已处理"""
        self._processed_msgids.add(msgid)
        # 限制去重集合大小，防止内存泄漏
        if len(self._processed_msgids) > 10000:
            # 移除一半旧的记录
            old_msgids = list(self._processed_msgids)[:5000]
            for old_msgid in old_msgids:
                self._processed_msgids.discard(old_msgid)
    
    def _cleanup_old_streams(self) -> None:
        """清理过期的流式消息缓存"""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        expired_streams = []
        for stream_id, data in self._cache.items():
            # 清理超过1小时的缓存
            if current_time - data['created_time'] > 3600:
                expired_streams.append(stream_id)
        
        for stream_id in expired_streams:
            self.remove_stream(stream_id)
        
        self._last_cleanup = current_time
        if expired_streams:
            logger.info(f"清理了 {len(expired_streams)} 个过期的流式消息缓存")


# 全局流式消息缓存实例
stream_cache = StreamMessageCache()
