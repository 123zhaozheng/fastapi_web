#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
企业微信智能机器人回调接口
处理企业微信的验证请求和消息回调
"""

import json
import logging
import base64
import hashlib
import io
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.utils.wecom_crypto import WXBizJsonMsgCrypt
from app.utils.wecom_message import (
    generate_random_string,
    make_text_stream,
    make_image_stream,
    make_mixed_stream,
    process_encrypted_image,
    parse_markdown_images,
    download_image,
    stream_cache,
    get_agent_id_from_aibot,
    make_welcome_template_card
)
from app.services.dify import DifyService

logger = logging.getLogger(__name__)

router = APIRouter()


def encrypt_message(receive_id: str, nonce: str, timestamp: str, stream: str) -> str:
    """
    加密消息
    
    Args:
        receive_id: 接收方ID（智能机器人为空字符串）
        nonce: 随机数
        timestamp: 时间戳
        stream: 流式消息内容
        
    Returns:
        加密后的消息
    """
    logger.info(f"开始加密消息，receive_id={receive_id}, nonce={nonce}, timestamp={timestamp}")
    logger.debug(f"发送流消息: {stream}")

    wxcpt = WXBizJsonMsgCrypt(
        settings.WECOM_TOKEN,
        settings.WECOM_ENCODING_AES_KEY,
        receive_id
    )
    ret, resp = wxcpt.EncryptMsg(stream, nonce, timestamp)
    if ret != 0:
        logger.error(f"加密失败，错误码: {ret}")
        raise HTTPException(status_code=500, detail="消息加密失败")

    stream_data = json.loads(stream)
    stream_id = stream_data['stream']['id']
    finish = stream_data['stream']['finish']
    logger.info(f"回调处理完成, 返回加密的流消息, stream_id={stream_id}, finish={finish}")
    logger.debug(f"加密后的消息: {resp}")

    return resp


async def process_dify_response(
    stream_id: str,
    user_query: str,
    user_id: str,
    receive_id: str,
    nonce: str,
    timestamp: str,
    agent: Optional[Agent] = None,
    images: Optional[list] = None
) -> None:
    """
    后台任务：处理 Dify 流式响应
    
    Args:
        stream_id: 流ID
        user_query: 用户查询
        user_id: 用户ID
        receive_id: 接收方ID
        nonce: 随机数
        timestamp: 时间戳
        agent: Agent实例
        images: 图片数据列表（二进制数据）
    """
    try:
        logger.info(f"开始处理 Dify 流式响应，stream_id={stream_id}, user_query={user_query}")
        
        # 创建流式消息缓存
        stream_cache.create_stream(stream_id, user_query)
        
        # 初始化 Dify 服务，如果有指定的 agent 则使用其配置
        if agent:
            dify_service = DifyService(api_key=agent.api_key, base_url=agent.api_endpoint)
            logger.info(f"使用 Agent {agent.name} 的 Dify 配置: {agent.api_endpoint}")
        else:
            dify_service = DifyService()
            logger.info("使用默认 Dify 配置")
        
        try:
            # 处理图片上传到 Dify
            uploaded_files = []
            if images:
                logger.info(f"开始上传 {len(images)} 张图片到 Dify")
                uploaded_files = await upload_images_to_dify(images, dify_service, user_id)
                logger.info(f"成功上传 {len(uploaded_files)} 张图片到 Dify")
            
            # 调用 Dify 流式 API，包含上传的文件
            async for chunk in dify_service.send_chat_message(
                query=user_query,
                user=user_id,
                files=uploaded_files if uploaded_files else None,
                streaming=True
            ):
                logger.debug(f"收到 Dify 响应块: {chunk}")
                
                # 处理不同类型的响应
                event = chunk.get('event', '')
                
                if event == 'message':
                    # 文本消息
                    answer = chunk.get('answer', '')
                    if answer:
                        stream_cache.add_text_part(stream_id, answer)
                        
                        # 解析可能的图片链接
                        # clean_text, images = parse_markdown_images(answer)
                        
                        # if images:
                        #     # 如果包含图片，异步下载并处理
                        #     await process_images_in_response(stream_id, images)
                        
                elif event == 'message_end':
                    # 消息结束
                    conversation_id = chunk.get('conversation_id')
                    if conversation_id:
                        stream_cache.set_conversation_id(stream_id, conversation_id)
                    
                    # 标记完成
                    stream_cache.mark_finished(stream_id)
                    logger.info(f"Dify 响应完成，stream_id={stream_id}")
                    break
                    
                elif event == 'error':
                    # 错误处理
                    error_msg = chunk.get('message', '处理请求时发生错误')
                    logger.error(f"Dify API 错误: {error_msg}")
                    
                    # 发送错误消息
                    error_stream = make_text_stream(stream_id, f"抱歉，{error_msg}", True)
                    stream_cache.mark_finished(stream_id)
                    break
        
        finally:
            await dify_service.close()
            
    except Exception as e:
        logger.error(f"处理 Dify 响应时出错: {str(e)}")
        # 发送错误消息
        error_stream = make_text_stream(stream_id, f"抱歉，处理请求时发生错误: {str(e)}", True)
        stream_cache.mark_finished(stream_id)


async def upload_images_to_dify(images: list, dify_service: DifyService, user_id: str) -> list:
    """
    上传图片到 Dify 服务
    
    Args:
        images: 图片二进制数据列表
        dify_service: Dify服务实例
        user_id: 用户ID
        
    Returns:
        上传成功的文件信息列表
    """
    uploaded_files = []
    
    for i, image_data in enumerate(images):
        try:
            # 确定图片格式
            image_format = "png"  # 默认格式
            if image_data.startswith(b'\xff\xd8\xff'):
                image_format = "jpg"
            elif image_data.startswith(b'\x89PNG'):
                image_format = "png"
            elif image_data.startswith(b'GIF'):
                image_format = "gif"
            elif image_data.startswith(b'RIFF') and b'WEBP' in image_data[:20]:
                image_format = "webp"
            
            filename = f"image_{i+1}.{image_format}"
            
            # 创建 UploadFile 对象
            file_obj = UploadFile(
                filename=filename,
                file=io.BytesIO(image_data),
                content_type=f"image/{image_format}"
            )
            
            # 上传到 Dify
            upload_response = await dify_service.upload_file(file_obj, user_id)
            
            # 构造文件信息
            file_info = {
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": upload_response.get("id")
            }
            
            uploaded_files.append(file_info)
            logger.info(f"成功上传图片到 Dify: {filename}")
            
        except Exception as e:
            logger.error(f"上传图片到 Dify 失败: {str(e)}")
            continue
    
    return uploaded_files


async def process_images_in_response(stream_id: str, images: list) -> None:
    """
    处理响应中的图片（Dify返回的Markdown图片链接）
    
    Args:
        stream_id: 流ID
        images: 图片信息列表
    """
    for image_info in images:
        url = image_info['url']
        success, image_data = await download_image(url)
        
        if success:
            stream_cache.add_image(stream_id, image_data)
            logger.info(f"成功下载并缓存图片: {url}")
        else:
            logger.error(f"下载图片失败: {url}, 错误: {image_data}")


@router.get("/callback/{botid}")
async def verify_url(
    request: Request,
    botid: str,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str
):
    """
    验证企业微信回调URL
    
    Args:
        botid: 机器人ID
        msg_signature: 消息签名
        timestamp: 时间戳
        nonce: 随机数
        echostr: 验证字符串
        
    Returns:
        验证结果
    """
    try:
        logger.info(f"收到URL验证请求，botid={botid}")
        
        # 企业创建的智能机器人的 VerifyUrl 请求, receiveid 是空串
        receive_id = settings.WECOM_RECEIVE_ID
        
        wxcpt = WXBizJsonMsgCrypt(
            settings.WECOM_TOKEN,
            settings.WECOM_ENCODING_AES_KEY,
            receive_id
        )
        
        ret, verified_echostr = wxcpt.VerifyURL(
            msg_signature,
            timestamp,
            nonce,
            echostr
        )
        
        if ret != 0:
            logger.error(f"URL验证失败，错误码: {ret}")
            verified_echostr = "verify fail"
        else:
            logger.info(f"URL验证成功，botid={botid}")
        
        return Response(content=verified_echostr, media_type="text/plain")
        
    except Exception as e:
        logger.error(f"URL验证异常: {str(e)}")
        return Response(content="verify fail", media_type="text/plain")


@router.post("/callback/{botid}")
async def handle_message(
    request: Request,
    botid: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    msg_signature: str = None,
    timestamp: str = None,
    nonce: str = None
):
    """
    处理企业微信消息回调
    
    Args:
        botid: 机器人ID
        background_tasks: 后台任务
        msg_signature: 消息签名
        timestamp: 时间戳
        nonce: 随机数
        
    Returns:
        处理结果
    """
    try:
        # 参数验证
        query_params = dict(request.query_params)
        if not all([msg_signature, timestamp, nonce]):
            logger.error("缺少必要参数")
            raise HTTPException(status_code=400, detail="缺少必要参数")
        
        logger.info(f"收到消息，botid={botid}, msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}")
        
        # 获取请求体
        post_data = await request.body()
        
        # 智能机器人的 receiveid 是空串
        receive_id = settings.WECOM_RECEIVE_ID
        
        # 解密消息
        wxcpt = WXBizJsonMsgCrypt(
            settings.WECOM_TOKEN,
            settings.WECOM_ENCODING_AES_KEY,
            receive_id
        )
        
        ret, decrypted_msg = wxcpt.DecryptMsg(
            post_data,
            msg_signature,
            timestamp,
            nonce
        )
        
        if ret != 0:
            logger.error(f"解密失败，错误码: {ret}")
            raise HTTPException(status_code=400, detail="解密失败")
        
        # 解析消息数据
        data = json.loads(decrypted_msg)
        logger.debug(f'解密后的数据: {data}')
        
        # 检查必要字段
        if 'msgtype' not in data:
            logger.info(f"不认识的事件: {data}")
            return Response(content="success", media_type="text/plain")
        
        # 消息去重检查
        msgid = data.get('msgid', '')
        if msgid and stream_cache.is_message_processed(msgid):
            logger.info(f"消息已处理过，跳过: msgid={msgid}")
            return Response(content="success", media_type="text/plain")
        
        # 提取新的字段
        msgtype = data['msgtype']
        aibotid = data.get('aibotid', '')
        chatid = data.get('chatid', '')
        chattype = data.get('chattype', 'single')
        from_info = data.get('from', {})
        user_id = from_info.get('userid', 'anonymous')
        
        # 标记消息已处理
        if msgid:
            stream_cache.mark_message_processed(msgid)
        
        # 根据 aibotid 查询对应的 Agent
        agent = None
        if aibotid:
            # 通过映射配置查询 agent_id
            mapped_agent_id = get_agent_id_from_aibot(aibotid)
            if mapped_agent_id:
                try:
                    agent_id = int(mapped_agent_id)
                    agent = db.query(Agent).filter(
                        Agent.id == agent_id,
                        Agent.is_active == True
                    ).first()
                    if not agent:
                        logger.warning(f"未找到激活的 Agent，agent_id={agent_id}")
                except ValueError:
                    logger.error(f"无效的 agent_id 格式: {mapped_agent_id}")
        
        logger.info(f"处理消息: msgtype={msgtype}, aibotid={aibotid}, chattype={chattype}, user_id={user_id}, agent={agent.name if agent else 'None'}")
        
        # 处理文本消息
        if msgtype == 'text':
            content = data['text']['content']
            
            # 生成流ID并启动后台任务处理
            stream_id = generate_random_string(16)
            
            # 立即返回初始响应
            initial_response = make_text_stream(stream_id, "正在思考中...", False)
            encrypted_response = encrypt_message(receive_id, nonce, timestamp, initial_response)
            
            # 添加后台任务处理 Dify 响应
            background_tasks.add_task(
                process_dify_response,
                stream_id,
                content,
                user_id,
                receive_id,
                nonce,
                timestamp,
                agent  # 传递 agent 对象
            )
            
            return Response(content=encrypted_response, media_type="text/plain")
        
        # 处理流式消息续传
        elif msgtype == 'stream':
            stream_id = data['stream']['id']
            
            # 检查流是否完成
            if stream_cache.is_finished(stream_id):
                # 获取完整内容
                current_content = stream_cache.get_current_content(stream_id)
                images = stream_cache.get_stream_data(stream_id).get('images', [])
                
                if images and current_content:
                    # 构造混合消息（文本+图片）
                    items = []
                    
                    # 添加文本
                    if current_content.strip():
                        items.append({
                            "msgtype": "text",
                            "text": {"content": current_content}
                        })
                    
                    # 添加图片（这些是Dify返回的Markdown图片）
                    for image_data in images:
                        image_md5 = hashlib.md5(image_data).hexdigest()
                        image_base64 = base64.b64encode(image_data).decode('utf-8')
                        items.append({
                            "msgtype": "image",
                            "image": {
                                "base64": image_base64,
                                "md5": image_md5
                            }
                        })
                    
                    final_response = make_mixed_stream(stream_id, items, True)
                elif images:
                    # 只有图片（Dify返回的）
                    final_response = make_image_stream(stream_id, images[0], True)
                else:
                    # 只有文本
                    final_response = make_text_stream(stream_id, current_content, True)
                
                # 清理缓存
                stream_cache.remove_stream(stream_id)
            else:
                # 返回当前进度
                current_content = stream_cache.get_current_content(stream_id)
                final_response = make_text_stream(stream_id, current_content, False)
            
            encrypted_response = encrypt_message(receive_id, nonce, timestamp, final_response)
            return Response(content=encrypted_response, media_type="text/plain")
        
        # 处理图片消息
        elif msgtype == 'image':
            image_url = data['image']['url']
            
            # 解密图片
            success, result = process_encrypted_image(image_url, settings.WECOM_ENCODING_AES_KEY)
            if not success:
                logger.error(f"图片处理失败: {result}")
                error_response = make_text_stream(
                    generate_random_string(16),
                    f"图片处理失败: {result}",
                    True
                )
                encrypted_response = encrypt_message(receive_id, nonce, timestamp, error_response)
                return Response(content=encrypted_response, media_type="text/plain")
            
            # 将图片上传到 Dify 并进行 AI 分析
            decrypted_data = result
            stream_id = generate_random_string(16)
            
            # 立即返回初始响应
            initial_response = make_text_stream(stream_id, "正在分析您的图片...", False)
            encrypted_response = encrypt_message(receive_id, nonce, timestamp, initial_response)
            
            # 添加后台任务处理图片分析
            background_tasks.add_task(
                process_dify_response,
                stream_id,
                "请分析这张图片",  # 默认提示词
                user_id,
                receive_id,
                nonce,
                timestamp,
                agent,  # 传递 agent 对象
                [decrypted_data]  # 传递图片数据列表
            )
            
            return Response(content=encrypted_response, media_type="text/plain")
        
        # 处理混合消息（图文混排）
        elif msgtype == 'mixed':
            logger.info("处理mixed消息类型")
            mixed_items = data.get('mixed', {}).get('msg_item', [])
            
            # 解析混合消息内容
            text_parts = []
            images = []
            
            for item in mixed_items:
                item_msgtype = item.get('msgtype', '')
                
                if item_msgtype == 'text':
                    text_content = item.get('text', {}).get('content', '')
                    if text_content:
                        text_parts.append(text_content)
                        
                elif item_msgtype == 'image':
                    image_url = item.get('image', {}).get('url', '')
                    if image_url:
                        # 解密图片
                        success, result = process_encrypted_image(image_url, settings.WECOM_ENCODING_AES_KEY)
                        if success:
                            images.append(result)
                        else:
                            logger.error(f"混合消息中图片处理失败: {result}")
            
            # 合并文本内容
            combined_text = '\n'.join(text_parts) if text_parts else ""
            
            if combined_text or images:
                # 生成流ID并启动后台任务处理
                stream_id = generate_random_string(16)
                
                # 立即返回初始响应
                if images and combined_text:
                    initial_message = "正在分析您的图文消息..."
                elif images:
                    initial_message = "正在分析您的图片..."
                else:
                    initial_message = "正在处理您的消息..."
                
                initial_response = make_text_stream(stream_id, initial_message, False)
                encrypted_response = encrypt_message(receive_id, nonce, timestamp, initial_response)
                
                # 添加后台任务处理 Dify 响应，传递图片数据
                background_tasks.add_task(
                    process_dify_response,
                    stream_id,
                    combined_text or "请分析这张图片",  # 如果没有文本，提供默认提示
                    user_id,
                    receive_id,
                    nonce,
                    timestamp,
                    agent,  # 传递 agent 对象
                    images  # 传递图片数据
                )
                
                return Response(content=encrypted_response, media_type="text/plain")
            
            else:
                # 空消息
                logger.warning("收到空的混合消息")
                return Response(content="success", media_type="text/plain")
        
        # 处理事件消息
        elif msgtype == 'event':
            event = data.get('event', '')
            logger.info(f"收到事件: {event}")
            
            # 处理进入会话事件
            if event.get('eventtype') == 'enter_chat':
                logger.info(f"用户 {user_id} 首次进入与机器人 {aibotid} 的会话")
                
                # 获取智能助手名称
                agent_name = agent.name if agent else "AI助手"
                
                # 构造欢迎卡片
                welcome_card_response = make_welcome_template_card(agent_name)
                
                # 加密并返回欢迎卡片
                encrypted_response = encrypt_message(aibotid, nonce, timestamp, welcome_card_response)
                return Response(content=encrypted_response, media_type="text/plain")
            
            else:
                logger.info(f"暂不处理的事件类型: {event}")
                return Response(content="success", media_type="text/plain")
        
        else:
            logger.warning(f"不支持的消息类型: {msgtype}")
            return Response(content="success", media_type="text/plain")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理消息时发生异常: {str(e)}")
        raise HTTPException(status_code=500, detail="内部服务器错误")
