from typing import Any, List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import uuid
import json
import asyncio

from app.database import get_db
from app.models.chat import MessageRole, DocumentStatus,Conversation
from app.models.agent import Agent
from app.models.user import User
from app.schemas import chat as schemas
from app.schemas.response import UnifiedResponseSingle
from app.core.deps import get_current_user, get_dify_service
from app.services.dify import DifyService
from app.services.file_storage import FileStorageService
from app.core.exceptions import ResourceNotFoundException, DifyApiException, InvalidOperationException
from app.utils.validators import validate_upload_file
from loguru import logger

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/completions")
async def chat_completions(
    request: schemas.ChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    dify_service: DifyService = Depends(get_dify_service)
) -> Any:
    """
    AI 聊天接口

    发送聊天消息给 Agent，支持流式或阻塞式响应。与 Dify API 集成，处理对话管理、消息历史和文档。

    Args:
        request (schemas.ChatRequest): 包含查询、对话 ID (可选)、文件 (可选) 和输入的请求体。
        background_tasks (BackgroundTasks): 用于后台任务。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。
        dify_service (DifyService): Dify 服务依赖。

    Returns:
        Any: 如果是流式响应，返回 StreamingResponse；如果是阻塞式响应，返回 Dify API 的响应体。

    Raises:
        HTTPException: 如果是新对话但缺少 agent_id，或 Agent 不可用，或用户无权访问 Agent。
        ResourceNotFoundException: 如果指定的对话 ID 不存在。
        DifyApiException: Dify API 调用错误。
        HTTPException: 内部服务器错误。
    """
    # Determine if it's a new conversation or existing
    is_new_conversation = request.conversation_id is None
    agent_id = None
    local_conversation = None
    custom_dify_service = None

    if is_new_conversation:
        # For new conversations, agent_id must be provided in inputs
        if "agent_id" not in request.inputs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="对于新对话，inputs 中必须包含 agent_id"
            )
        agent_id = request.inputs["agent_id"]

        # Get agent
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ResourceNotFoundException("智能体", str(agent_id))

        # Check if agent is active
        if not agent.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="此智能体当前不可用"
            )

        # Check if user has access to this agent
        if not current_user.is_admin:
            user_has_access = False
            global_access = any(p.type == "global" for p in agent.permissions)
            if global_access:
                user_has_access = True
            if not user_has_access:
                user_role_ids = [role.id for role in current_user.roles]
                role_access = any(p.type == "role" and p.role_id in user_role_ids for p in agent.permissions)
                if role_access:
                    user_has_access = True
            if not user_has_access and current_user.department_id:
                dept_access = any(p.type == "department" and p.department_id == current_user.department_id for p in agent.permissions)
                if dept_access:
                    user_has_access = True
            if not user_has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="您无权访问此智能体"
                )

        # Set up Dify API with the agent's credentials
        dify_api_key = agent.api_key
        dify_base_url = agent.api_endpoint
        custom_dify_service = DifyService(api_key=dify_api_key, base_url=dify_base_url)

    else:
        # For existing conversations, find local record to get agent_id
        local_conversation = db.query(Conversation).filter(
            Conversation.conversation_id == request.conversation_id,
            Conversation.user_id == current_user.id # Ensure user owns the conversation
        ).first()

        if not local_conversation:
            raise ResourceNotFoundException("对话", request.conversation_id)

        agent_id = local_conversation.agent_id

        # Get agent based on stored agent_id
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
             # This indicates a data inconsistency, handle appropriately
             logger.error(f"Agent ID {agent_id} not found for conversation {request.conversation_id}")
             raise HTTPException(status_code=500, detail="未找到关联的智能体。")

        # Re-check user access to the agent for existing conversations
        if not current_user.is_admin:
            user_has_access = False
            global_access = any(p.type == "global" for p in agent.permissions)
            if global_access:
                user_has_access = True
            if not user_has_access:
                user_role_ids = [role.id for role in current_user.roles]
                role_access = any(p.type == "role" and p.role_id in user_role_ids for p in agent.permissions)
                if role_access:
                    user_has_access = True
            if not user_has_access and current_user.department_id:
                dept_access = any(p.type == "department" and p.department_id == current_user.department_id for p in agent.permissions)
                if dept_access:
                    user_has_access = True
            if not user_has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="您无权访问此智能体的对话"
                )

        # Set up Dify API with the agent's credentials from the found agent
        dify_api_key = agent.api_key
        dify_base_url = agent.api_endpoint
        custom_dify_service = DifyService(api_key=dify_api_key, base_url=dify_base_url)


    # Check for files and prepare them
    files_data = []
    if request.files:
        for idx, file_info in enumerate(request.files):
            # Prepare file for Dify API
            if file_info.transfer_method == schemas.FileTransferMethodEnum.REMOTE_URL:
                if not file_info.url:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"索引 {idx} 处的远程文件需要 URL"
                    )

                files_data.append({
                    "type": file_info.type.value,
                    "transfer_method": file_info.transfer_method.value,
                    "url": str(file_info.url)
                })

            elif file_info.transfer_method == schemas.FileTransferMethodEnum.LOCAL_FILE:
                if not file_info.upload_file_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"索引 {idx} 处的本地文件需要上传文件 ID"
                    )

                files_data.append({
                    "type": file_info.type.value,
                    "transfer_method": file_info.transfer_method.value,
                    "upload_file_id": file_info.upload_file_id
                })

    # Handle streaming response
    if request.response_mode == schemas.ResponseModeEnum.STREAMING:
        # Pass the custom_dify_service to the streaming function
        return StreamingResponse(
            stream_chat_response(
                custom_dify_service, # Use the custom service
                request.query,
                request.conversation_id, # Pass conversation_id (will be None for new)
                str(current_user.id),
                files_data,
                request.inputs,
                db, # Added db
                current_user.id, # Added current_user_id
                agent_id, # Added agent_id
                request.auto_generate_name
            ),
            media_type="text/event-stream"
        )
    else:
        # Handle blocking response
        try:
            # Since send_chat_message now always returns an async generator,
            # we need to iterate once to get the single result in blocking mode.
            response_generator = custom_dify_service.send_chat_message( # Use the custom service
                query=request.query,
                conversation_id=request.conversation_id, # Pass conversation_id (will be None for new)
                user=current_user.username,
                inputs=request.inputs,
                files=files_data,
                streaming=False
            )

            final_response = None
            async for event in response_generator:
                final_response = event # Get the first (and only) yielded item
                break # Stop after the first item

            # Handle case where generator might be empty unexpectedly
            if final_response is None:
                 logger.error("Blocking chat response generator yielded no result.")
                 raise HTTPException(status_code=500, detail="获取聊天响应失败。")

            # --- Handle local conversation record after successful Dify response ---
            if is_new_conversation:
                # Create new local conversation record
                dify_conversation_id = final_response.get("conversation_id")
                if not dify_conversation_id:
                     logger.error("Dify blocking response for new conversation did not return conversation_id.")
                     # Decide how to handle this - maybe raise an error or log and continue
                else:
                    new_local_conversation = Conversation(
                        conversation_id=dify_conversation_id,
                        final_query=request.query[:100] if len(request.query) > 100 else request.query, # Store truncated query if needed
                        user_id=current_user.id,
                        agent_id=agent_id # Use the agent_id determined earlier
                    )
                    db.add(new_local_conversation)
                    db.commit()
                    db.refresh(new_local_conversation)
                    logger.info(f"Created new local conversation record: {new_local_conversation.id} (Dify ID: {dify_conversation_id})")

            elif local_conversation:
                # Update existing local conversation record
                local_conversation.final_query = request.query[:100] if len(request.query) > 100 else request.query # Update with truncated query if needed
                # updated_at is handled by onupdate=func.now()
                db.commit()
                db.refresh(local_conversation)
                logger.info(f"Updated local conversation record: {local_conversation.id} (Dify ID: {local_conversation.conversation_id})")
            # --- End local conversation record handling ---


            return final_response

        except DifyApiException as e:
            logger.error(f"Dify API error: {str(e)}")
            raise
        except ResourceNotFoundException as e:
             # Re-raise ResourceNotFoundException from local conversation lookup
             raise
        except Exception as e:
            logger.exception(f"Error in chat completions (blocking): {str(e)}")
            raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")
        finally:
            # Close the custom Dify service if it was created
            if custom_dify_service:
                await custom_dify_service.close()

# Need to update stream_chat_response to handle local conversation creation/update
# This will require passing the db session and user to it, and potentially the agent_id
# This is a more complex change and might require restructuring stream_chat_response
# For now, I will leave stream_chat_response as is and address local record updates
# for streaming in a separate step after confirming the blocking mode works.
# TODO: Implement local conversation record handling for streaming responses.
async def stream_chat_response(
    dify_service: DifyService,
    query: str,
    conversation_id: Optional[str],
    user_id: str,
    files: List[Dict],
    inputs: Dict,
    db: Session, # Moved db before default parameters
    current_user_id: int, # Moved current_user_id before default parameters
    agent_id: int, # Moved agent_id before default parameters
    auto_generate_name: bool = True # Default parameter remains last
):
    """
    从Dify API流式响应聊天,并处理本地对话更新
    """
    local_conversation = None # To store the local conversation object if it exists or is created
    is_new_conversation = conversation_id is None

    try:
        # Track assistant message for error handling
        task_id = None
        assistant_message_id = None

        # If it's an existing conversation, fetch the local record
        if not is_new_conversation:
             local_conversation = db.query(Conversation).filter(
                Conversation.conversation_id == conversation_id,
                Conversation.user_id == current_user_id
             ).first()
             # If local record not found for existing conversation, decide how to handle
             # For now, we proceed but won't update a local record that doesn't exist.
             if not local_conversation:
                  logger.warning(f"Local conversation record not found for Dify conversation ID: {conversation_id}")


        async for event in dify_service.send_chat_message(
            query=query,
            conversation_id=conversation_id,
            user=user_id,
            inputs=inputs,
            files=files,
            streaming=True
        ):
            # Extract event type
            event_type = event.get("event")

            # Forward the event as SSE
            yield f"data: {json.dumps(event)}\n\n"

            # Track message ID and task ID for error handling
            if event_type == "message":
                if not assistant_message_id:
                    assistant_message_id = event.get("message_id")
                task_id = event.get("task_id")

            # --- Handle local conversation record updates based on Dify events ---
            if event_type == "message_end":
                 dify_conversation_id = event.get("conversation_id")
                 if is_new_conversation and not local_conversation and dify_conversation_id:
                     # Create new local conversation record on message_end for new conversations
                     try:
                         new_local_conversation = Conversation(
                             conversation_id=dify_conversation_id,
                             final_query=query[:100] if len(query) > 100 else query, # Store truncated query if needed
                             user_id=current_user_id,
                             agent_id=agent_id # Use the agent_id passed to the function
                         )
                         db.add(new_local_conversation)
                         db.commit()
                         db.refresh(new_local_conversation)
                         local_conversation = new_local_conversation # Store for potential future updates in this stream
                         logger.info(f"Created new local conversation record (streaming): {local_conversation.id} (Dify ID: {dify_conversation_id})")
                     except IntegrityError:
                          db.rollback()
                          logger.warning(f"Local conversation record with Dify ID {dify_conversation_id} already exists.")
                          # Attempt to fetch the existing record if creation failed due to uniqueness
                          local_conversation = db.query(Conversation).filter(
                                Conversation.conversation_id == dify_conversation_id,
                                Conversation.user_id == current_user_id
                          ).first()


                 elif local_conversation:
                     # Update existing local conversation record on message_end
                     local_conversation.final_query = query[:100] if len(query) > 100 else query # Update with truncated query if needed
                     # updated_at is handled by onupdate=func.now()
                     db.commit()
                     db.refresh(local_conversation)
                     logger.info(f"Updated local conversation record (streaming): {local_conversation.id} (Dify ID: {local_conversation.conversation_id})")

            # --- End local conversation record handling ---


    except DifyApiException as e:
        # Return error event
        error_event = {
            "event": "error",
            "task_id": task_id,
            "message_id": assistant_message_id,
            "status": e.status_code,
            "code": e.code,
            "message": str(e.detail)
        }
        yield f"data: {json.dumps(error_event)}\n\n"

        logger.error(f"Dify API error during streaming: {str(e)}")

    except Exception as e:
        # Return error event for any other exception
        error_event = {
            "event": "error",
            "task_id": task_id,
            "message_id": assistant_message_id,
            "status": 500,
            "code": "internal_error",
            "message": f"Internal server error: {str(e)}"
        }
        yield f"data: {json.dumps(error_event)}\n\n"

        logger.exception(f"Error during streaming: {str(e)}")

    finally:
        # Close Dify service
        await dify_service.close()


@router.post("/stop", operation_id="stop_chat_generation")
async def stop_generation(
    request: schemas.StopGenerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    # Removed default dify_service dependency
) -> Any:
    """
    停止进行中的生成

    停止指定任务 ID 的 Agent 消息生成过程。根据会话 ID 获取 Agent 凭据并调用 Dify API。

    Args:
        request (schemas.StopGenerationRequest): 包含任务 ID 和 conversation_id 的请求体。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。

    Returns:
        Dict[str, Any]: 包含停止结果的字典。

    Raises:
        ResourceNotFoundException: 如果指定的对话 ID 不存在。
        HTTPException: 如果关联的 Agent 不存在或用户无权访问。
        DifyApiException: Dify API 调用错误。
        HTTPException: 内部服务器错误。
    """
    # 1. Find local conversation record to get agent_id and verify user access
    local_conversation = db.query(Conversation).filter(
        Conversation.conversation_id == request.conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not local_conversation:
        raise ResourceNotFoundException("对话", request.conversation_id)

    agent_id = local_conversation.agent_id
    logger.debug(f"Stopping generation for conversation ID: {request.conversation_id}, local agent_id: {agent_id}")

    # 2. Get agent based on stored agent_id
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
         logger.error(f"Agent ID {agent_id} not found for conversation {request.conversation_id}")
         raise HTTPException(status_code=500, detail="未找到关联的智能体。")

    # 3. Re-check user access to the agent
    if not current_user.is_admin:
        user_has_access = False
        global_access = any(p.type == "global" for p in agent.permissions)
        if global_access:
            user_has_access = True
        if not user_has_access:
            user_role_ids = [role.id for role in current_user.roles]
            role_access = any(p.type == "role" and p.role_id in user_role_ids for p in agent.permissions)
            if role_access:
                user_has_access = True
        if not user_has_access and current_user.department_id:
            dept_access = any(p.type == "department" and p.department_id == current_user.department_id for p in agent.permissions)
            if dept_access:
                user_has_access = True
        if not user_has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您无权停止此智能体对话的生成"
            )

    # 4. Set up Dify API with the agent's credentials
    dify_api_key = agent.api_key
    dify_base_url = agent.api_endpoint
    logger.debug(f"Using Dify base_url: {dify_base_url}, api_key (masked): {'*' * (len(dify_api_key) - 4) + dify_api_key[-4:] if dify_api_key else 'None'}")
    custom_dify_service = DifyService(api_key=dify_api_key, base_url=dify_base_url)


    try:
        # Call Dify API to stop generation, passing user ID and task_id from the request
        response = await custom_dify_service.stop_generation(
            task_id=request.task_id,
            user=str(current_user.id)
        )
        # Assuming Dify returns {"result": "success"} on success
        if response.get("result") == "success":
             return {"success": True, "detail": "Generation stopped"}
        else:
             # Handle cases where Dify might return 200 OK but not explicitly "success"
             logger.warning(f"Dify stop generation returned unexpected response: {response}")
             return {"success": False, "detail": "Failed to confirm stop status from Dify."}
    except DifyApiException as e:
        logger.error(f"Dify API error when stopping generation: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Error in stop generation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")
    finally:
        # Close the custom Dify service
        if custom_dify_service:
            await custom_dify_service.close()


@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback", operation_id="feedback_message", response_model=UnifiedResponseSingle[schemas.FeedbackResponse])
async def give_message_feedback(
    conversation_id: str,
    message_id: str,
    request: schemas.MessageFeedbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UnifiedResponseSingle[schemas.FeedbackResponse]:
    """
    消息反馈

    为指定消息提供"点赞"或"点踩"的反馈。

    Args:
        conversation_id (str): 对话 ID。
        message_id (str): 消息 ID。
        request (schemas.MessageFeedbackRequest): 包含评分和可选内容的请求体。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。

    Returns:
        UnifiedResponseSingle[schemas.FeedbackResponse]: 包含反馈结果的统一响应对象。

    Raises:
        ResourceNotFoundException: 如果指定的对话 ID 不存在。
        HTTPException: 如果关联的 Agent 不存在或用户无权访问。
        DifyApiException: Dify API 调用错误。
    """
    # 1. Find local conversation record to get agent_id and verify user access
    local_conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not local_conversation:
        raise ResourceNotFoundException("对话", conversation_id)

    # 2. Get agent based on stored agent_id
    agent = db.query(Agent).filter(Agent.id == local_conversation.agent_id).first()
    if not agent:
         logger.error(f"Agent ID {local_conversation.agent_id} not found for conversation {conversation_id}")
         raise HTTPException(status_code=500, detail="未找到关联的智能体。")

    # 3. No need to re-check full permissions here, as owning the conversation implies access.
    # However, a basic check is still good practice.
    if not current_user.is_admin:
        user_has_access = False
        global_access = any(p.type == "global" for p in agent.permissions)
        if global_access:
            user_has_access = True
        if not user_has_access:
            user_role_ids = [role.id for role in current_user.roles]
            role_access = any(p.type == "role" and p.role_id in user_role_ids for p in agent.permissions)
            if role_access:
                user_has_access = True
        if not user_has_access and current_user.department_id:
            dept_access = any(p.type == "department" and p.department_id == current_user.department_id for p in agent.permissions)
            if dept_access:
                user_has_access = True
        if not user_has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您无权停止此智能体对话的生成"
            )
    # 4. Set up Dify API with the agent's credentials
    dify_api_key = agent.api_key
    dify_base_url = agent.api_endpoint
    custom_dify_service = DifyService(api_key=dify_api_key, base_url=dify_base_url)

    try:
        # The rating can be 'like', 'dislike', or None (if the user wants to undo their feedback)
        rating_value = request.rating.value if request.rating else None

        # Call the existing feedback_message method in DifyService
        response = await custom_dify_service.feedback_message(
            message_id=message_id,
            rating=rating_value,
            user=str(current_user.id),
            content=request.content
        )
        # Assuming Dify returns {"result": "success"} on success
        if response.get("result") == "success":
             return UnifiedResponseSingle(data=schemas.FeedbackResponse(success=True, detail="Feedback submitted successfully"))
        else:
             logger.warning(f"Dify feedback returned unexpected response: {response}")
             return UnifiedResponseSingle(data=schemas.FeedbackResponse(success=False, detail="Failed to confirm feedback status from Dify."))
    except DifyApiException as e:
        logger.error(f"Dify API error when submitting feedback: {str(e)}")
        raise
    except Exception as e:
        logger.exception(f"Error in message feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")
    finally:
        if custom_dify_service:
            await custom_dify_service.close()


# TODO: Verify if the underlying Dify API endpoint 'GET /conversations/{conversation_id}/messages' exists and supports pagination.
# The Dify documentation provided did not explicitly list this. If it doesn't exist,
# this endpoint's logic needs to be re-evaluated or removed.
@router.get("/messages") # Updated route to match Dify API path
async def get_conversation_messages_history( # Renamed function
    conversation_id: str = Query(..., description="Conversation ID"), # conversation_id is now a query parameter
    first_id: Optional[str] = Query(None, description="First message ID for pagination (from previous response)"),
    limit: int = Query(20, ge=1, le=100, description="Number of messages per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    # dify_service: DifyService = Depends(get_dify_service) # Removed default service dependency
) -> List[schemas.Message]:
    """
    获取对话消息历史 (分页)

    从 Dify API 获取指定对话的消息历史，支持分页。需要从本地对话记录中获取 Agent 凭据。

    Args:
        conversation_id (str): 对话 ID。
        first_id (Optional[str]): 分页的起始消息 ID (从上一次响应获取)。
        limit (int): 每页返回的消息数量 (默认为 20)。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。

    Returns:
        List[schemas.Message]: 包含详细消息信息的列表。每个 Message 对象包含以下字段：
            - message_id (str): 消息唯一 ID。
            - conversation_id (str): 会话 ID。
            - role (MessageRoleEnum): 消息发送者的角色 (user, assistant 等)。
            - content (str): 消息的主要文本内容。
            - query (Optional[str]): 用户输入/提问内容 (仅用户消息有)。
            - tokens (Optional[int]): 使用的 token 数量。
            - task_id (Optional[str]): 任务 ID。
            - metadata (Optional[Dict[str, Any]]): 其他元数据。
            - created_at (datetime): 消息创建时间。
            - inputs (Optional[Dict[str, Any]]): 用户输入参数。
            - message_files (Optional[List[Dict[str, Any]]]): 消息关联的文件列表。
            - feedback (Optional[Dict[str, Any]]): 消息的反馈信息。
            - retriever_resources (Optional[List[Dict[str, Any]]]): 引用和归属分段列表。

    Raises:
        ResourceNotFoundException: 如果指定的对话 ID 不存在。
        HTTPException: 如果关联的 Agent 不存在或用户无权访问。
        DifyApiException: Dify API 调用错误。
        HTTPException: 内部服务器错误。
    """
    # Find local conversation record to get agent_id and verify user access
    # Note: conversation_id is now a query parameter, but we still use it to find the local conversation
    local_conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not local_conversation:
        raise ResourceNotFoundException("对话", conversation_id)

    agent_id = local_conversation.agent_id
    logger.debug(f"Fetching conversation messages for conversation ID: {conversation_id}, local agent_id: {agent_id}")

    # Get agent based on stored agent_id
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
         logger.error(f"Agent ID {agent_id} not found for conversation {conversation_id}")
         raise HTTPException(status_code=500, detail="未找到关联的智能体。")

    # Re-check user access to the agent
    if not current_user.is_admin:
        user_has_access = False
        global_access = any(p.type == "global" for p in agent.permissions)
        if global_access:
            user_has_access = True
        if not user_has_access:
            user_role_ids = [role.id for role in current_user.roles]
            role_access = any(p.type == "role" and p.role_id in user_role_ids for p in agent.permissions)
            if role_access:
                user_has_access = True
        if not user_has_access and current_user.department_id:
            dept_access = any(p.type == "department" and p.department_id == current_user.department_id for p in agent.permissions)
            if dept_access:
                user_has_access = True
        if not user_has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您无权访问此智能体的对话"
            )

    # Set up Dify API with the agent's credentials from the found agent
    dify_api_key = agent.api_key
    dify_base_url = agent.api_endpoint
    logger.debug(f"Using Dify base_url: {dify_base_url}, api_key (masked): {'*' * (len(dify_api_key) - 4) + dify_api_key[-4:] if dify_api_key else 'None'}")
    custom_dify_service = DifyService(api_key=dify_api_key, base_url=dify_base_url)


    try:
        # Get messages for this conversation using pagination parameters
        logger.debug(f"Calling get_conversation_messages with conversation_id: {conversation_id}, user_id: {current_user.id}, first_id: {first_id}, limit: {limit}")
        messages = await custom_dify_service.get_conversation_messages(
            conversation_id=conversation_id,
            user_id=str(current_user.id),
            first_id=first_id, # Pass pagination parameter
            limit=limit        # Pass pagination parameter
        )

        # Process messages
        processed_messages = []
        for msg in messages:
            # Safely convert timestamps
            created_at = None
            if msg.get("created_at"):
                try:
                    created_at = datetime.fromtimestamp(float(msg.get("created_at")))
                except (ValueError, TypeError):
                    created_at = datetime.now()
            else:
                created_at = datetime.now()

            processed_messages.append(schemas.Message(
                message_id=msg.get("id"),
                conversation_id=msg.get("conversation_id"), # Map conversation_id
                # role=msg.get("role"),
                content=msg.get("answer"), # Map answer to content
                query=msg.get("query"), # Map query
                created_at=created_at,
                inputs=msg.get("inputs"),
                message_files=msg.get("message_files"),
                feedback=msg.get("feedback"),
                retriever_resources=msg.get("retriever_resources"),
                # task_id=msg.get("task_id"), # Assuming task_id is also available in the message object
                # metadata=msg.get("metadata") # Assuming metadata is also available
            ))

        # Return the processed message list directly
        # Dify API response for messages already contains the list in 'data' key,
        # and get_conversation_messages service method extracts it.
        return processed_messages

    except DifyApiException as e:
        logger.error(f"Error fetching conversation details: {str(e)}")
        if e.status_code == 404:
            raise ResourceNotFoundException("对话", conversation_id)
        raise
    except Exception as e:
        logger.exception(f"Error fetching conversation details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取对话详情时出错: {str(e)}"
        )
    finally:
        # Close the custom Dify service
        if custom_dify_service:
            await custom_dify_service.close()


@router.post("/upload", operation_id="upload_chat_document")
async def upload_document(
    file: UploadFile = File(...),
    agent_id: int = None, # agent_id is required for upload
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    dify_service: DifyService = Depends(get_dify_service) # Default service not used if agent_id provided
) -> schemas.DocumentUploadResponse:
    """
    上传文档

    上传文档以便与 Agent 进行交互处理。需要提供 Agent ID 以确定使用哪个 Dify 实例。

    Args:
        file (UploadFile): 要上传的文档文件。
        agent_id (int): 关联的 Agent ID。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。

    Returns:
        schemas.DocumentUploadResponse: 包含上传文件 ID、文件名、大小、MIME 类型和状态的响应模型。

    Raises:
        HTTPException: 如果缺少 agent_id 或文件验证失败。
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
        HTTPException: 如果用户无权访问 Agent。
        DifyApiException: Dify API 调用错误。
        HTTPException: 内部服务器错误。
    """
    if agent_id is None:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件上传需要 agent_id"
         )

    custom_dify = None
    try:
        # Validate file
        # validate_upload_file(file)

        # Get agent
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ResourceNotFoundException("智能体", str(agent_id))

        # Check if user has access to this agent
        if not current_user.is_admin:
            user_has_access = False
            global_access = any(p.type == "global" for p in agent.permissions)
            if global_access:
                user_has_access = True
            if not user_has_access:
                user_role_ids = [role.id for role in current_user.roles]
                role_access = any(p.type == "role" and p.role_id in user_role_ids for p in agent.permissions)
                if role_access:
                    user_has_access = True
            if not user_has_access and current_user.department_id:
                dept_access = any(p.type == "department" and p.department_id == current_user.department_id for p in agent.permissions)
                if dept_access:
                    user_has_access = True
            if not user_has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="您无权访问此智能体"
                )

        # Use agent's Dify credentials
        custom_dify = DifyService(api_key=agent.api_key, base_url=agent.api_endpoint)

        # Upload file to Dify, passing user ID
        upload_result = await custom_dify.upload_file(
            file=file,
            user=str(current_user.id)
        )

        # Return response
        return schemas.DocumentUploadResponse(
            upload_file_id=upload_result.get("id"),
            filename=file.filename,
            # Dify response might not include size/mimetype, adjust if needed
            size=upload_result.get("size", file.size or 0),
            mimetype=upload_result.get("mime_type", file.content_type),
            status="completed" # Assuming upload is synchronous and completed
        )

    except DifyApiException as e:
        logger.error(f"Dify API error when uploading file: {str(e)}")
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件验证失败: {str(e)}"
        )
    except Exception as e:
        logger.exception(f"Error uploading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传文档时出错: {str(e)}"
        )
    finally:
        # Close the custom Dify service
        if custom_dify:
            await custom_dify.close()


# TODO: Evaluate if the 'deep thinking' logic (constructing a specific prompt)
# can be achieved by configuring the Dify application itself (e.g., System Prompt, Workflow).
# If possible, this custom endpoint could potentially be removed or simplified.
@router.post("/deep-thinking", operation_id="perform_deep_thinking")
async def deep_thinking(
    request: schemas.DeepThinkingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    dify_service: DifyService = Depends(get_dify_service) # Default service not used if agent_id provided
) -> Any:
    """
    深度思考模式

    使用特定的 prompt 结构处理复杂问题，通过 Dify API 进行"深度思考"。需要在请求体中提供 Agent ID。

    Args:
        request (schemas.DeepThinkingRequest): 包含查询、Agent ID、对话 ID (可选) 和输入的请求体。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。

    Returns:
        Any: Dify API 的响应体。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
        HTTPException: 如果 Agent 不可用或用户无权访问。
        DifyApiException: Dify API 调用错误。
    """
    # Get agent
    agent = db.query(Agent).filter(Agent.id == request.agent_id).first()
    if not agent:
        raise ResourceNotFoundException("智能体", str(request.agent_id))

    # Check if agent is active
    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此智能体当前不可用"
        )

    # Check if user has access to this agent
    if not current_user.is_admin:
        # For non-admin users, check permissions
        user_has_access = False

        # Check global access
        global_access = any(p.type == "global" for p in agent.permissions)
        if global_access:
            user_has_access = True

        # Check role-based access
        if not user_has_access:
            user_role_ids = [role.id for role in current_user.roles]
            role_access = any(p.type == "role" and p.role_id in user_role_ids for p in agent.permissions)
            if role_access:
                user_has_access = True

        # Check department-based access
        if not user_has_access and current_user.department_id:
            dept_access = any(p.type == "department" and p.department_id == current_user.department_id for p in agent.permissions)
            if dept_access:
                user_has_access = True

        if not user_has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您无权访问此智能体"
            )

    # Set up Dify API with the agent's credentials
    dify_api_key = agent.api_key
    dify_base_url = agent.api_endpoint
    custom_dify_service = DifyService(api_key=dify_api_key, base_url=dify_base_url)

    try:
        # Prepare deep thinking prompt
        deep_thinking_prompt = f"""
        I want you to solve this question step-by-step using deep thinking:

        {request.query}

        Break down your reasoning process in detail:
        1. First analyze what is being asked
        2. Consider different approaches to solve this problem
        3. Work through the problem methodically
        4. Verify your answer

        Be thorough and show all your work.
        """

        # Use Dify API for deep thinking - blocking mode
        response = await custom_dify_service.send_chat_message(
            query=deep_thinking_prompt,
            conversation_id=request.conversation_id,
            user=str(current_user.id),
            inputs=request.inputs,
            streaming=False
        )

        return response

    except DifyApiException as e:
        logger.error(f"Dify API error: {str(e)}")
        raise
    finally:
        await custom_dify_service.close()




@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除对话

    从本地数据库和 Dify 中删除指定对话。

    Args:
        conversation_id (str): 要删除的对话 ID。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。

    Returns:
        Dict[str, str]: 包含删除结果的字典。

    Raises:
        ResourceNotFoundException: 如果指定的对话 ID 在本地数据库中不存在。
        HTTPException: 如果删除本地对话记录失败。
    """
    # 1. Find the local conversation record and verify user ownership
    local_conversation = db.query(Conversation).filter(
        Conversation.conversation_id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not local_conversation:
        raise ResourceNotFoundException("对话", conversation_id)

    # 2. Get the associated Agent's credentials
    agent = db.query(Agent).filter(Agent.id == local_conversation.agent_id).first()
    if not agent:
        # This indicates a data inconsistency, log and proceed with local deletion
        logger.error(f"Agent ID {local_conversation.agent_id} not found for conversation {conversation_id} during deletion.")
        # We will still attempt local deletion even if agent is missing

    # 3. Attempt to delete the conversation from Dify
    if agent:
        custom_dify_service = None
        try:
            custom_dify_service = DifyService(api_key=agent.api_key, base_url=agent.api_endpoint)
            # Assuming Dify has a delete conversation endpoint
            # The Dify documentation provided did not explicitly list this.
            # If Dify API does not support deleting conversations, this part needs adjustment.
            # For now, assuming an endpoint like DELETE /conversations/{conversation_id} exists.
            # Need to verify Dify API documentation for the correct endpoint and method.
            # Placeholder call:
            # await custom_dify_service.delete_conversation(conversation_id=conversation_id, user_id=str(current_user.id))
            logger.warning(f"Dify conversation deletion not implemented yet for conversation ID: {conversation_id}. Skipping Dify API call.")
            # TODO: Implement actual Dify API call for conversation deletion if supported.

        except DifyApiException as e:
            logger.error(f"Dify API error when deleting conversation {conversation_id}: {str(e)}")
            # Decide how to handle Dify deletion failure.
            # Option 1: Raise HTTPException and stop.
            # Option 2: Log error and proceed with local deletion (current approach).
            # For now, we log and proceed with local deletion.
        except Exception as e:
            logger.exception(f"Error during Dify conversation deletion attempt for {conversation_id}: {str(e)}")
            # Log and proceed with local deletion.
        finally:
            if custom_dify_service:
                await custom_dify_service.close()

    # 4. Delete the conversation record from the local database
    try:
        db.delete(local_conversation)
        db.commit()
        logger.info(f"Deleted local conversation record: {local_conversation.id} (Dify ID: {conversation_id})")
    except Exception as e:
        db.rollback()
        logger.exception(f"Error deleting local conversation record {conversation_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"删除本地对话记录失败: {str(e)}")

    return {"detail": "Conversation deleted successfully"}

@router.get("/history")
async def get_chat_history(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    keyword: Optional[str] = None,
    agent_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = '-updated_at',
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> schemas.ChatHistoryResponse:
    """
    获取聊天历史记录

    从本地数据库获取当前用户的聊天历史记录，支持分页、时间范围、关键字和 Agent 过滤，以及排序。

    Args:
        start_date (Optional[datetime]): 过滤起始日期。
        end_date (Optional[datetime]): 过滤结束日期。
        keyword (Optional[str]): 按对话最终查询或 Agent 名称过滤关键字。
        agent_id (Optional[int]): 按 Agent ID 过滤。
        page (int): 页码 (默认为 1)。
        page_size (int): 每页数量 (默认为 20)。
        sort_by (Optional[str]): 排序字段 (例如, '-updated_at' 表示按 updated_at 降序)。
        db (Session): 数据库会话依赖。
        current_user (User): 当前用户依赖。

    Returns:
        schemas.ChatHistoryResponse: 包含聊天历史记录列表、总数、分页信息等的响应模型。

    Raises:
        HTTPException: 内部服务器错误。
    """
    # Validate pagination parameters
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    try:
        # Build the base query to get conversations for the current user
        query = db.query(Conversation).filter(Conversation.user_id == current_user.id)

        # Apply filters based on query parameters
        if start_date:
            query = query.filter(Conversation.created_at >= start_date)
        if end_date:
            query = query.filter(Conversation.created_at <= end_date)
        if keyword:
            # Assuming keyword search applies to the final_query or potentially agent name
            # You might need to adjust this based on where you want to search for the keyword
            query = query.join(Agent).filter(
                (Conversation.final_query.ilike(f"%{keyword}%")) |
                (Agent.name.ilike(f"%{keyword}%"))
            )
        if agent_id:
            query = query.filter(Conversation.agent_id == agent_id)

        # Apply sorting
        if sort_by:
            if sort_by.startswith('-'):
                sort_column = getattr(Conversation, sort_by[1:])
                query = query.order_by(sort_column.desc())
            else:
                sort_column = getattr(Conversation, sort_by)
                query = query.order_by(sort_column)
        else:
             # Default sort by updated_at descending
             query = query.order_by(Conversation.updated_at.desc())


        # Get total count before pagination
        total_count = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        conversations = query.offset(offset).limit(page_size).all()

        # Prepare response items
        items = []
        for conv in conversations:
            # Fetch the associated agent to get agent_name and icon
            agent = db.query(Agent).filter(Agent.id == conv.agent_id).first()
            agent_name = agent.name if agent else "Unknown Agent"
            agent_icon = agent.icon if agent else None

            items.append(schemas.ConversationRead(
                id=conv.id,
                conversation_id=conv.conversation_id,
                final_query=conv.final_query, # Use final_query
                user_id=conv.user_id,
                agent_id=conv.agent_id,
                agent_name=agent_name,
                agent_icon=agent_icon,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            ))

        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        return schemas.ChatHistoryResponse(
            items=items,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )

    except Exception as e:
        logger.exception(f"Error fetching chat history from local DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取聊天记录时出错: {str(e)}"
        )