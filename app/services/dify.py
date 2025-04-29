import json
import os
from typing import Dict, Any, Optional, List, AsyncGenerator
import httpx
from fastapi import UploadFile
from fastapi.encoders import jsonable_encoder
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.core.exceptions import DifyApiException


class DifyService:
    """
    Service for integrating with Dify API
    """
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or settings.DIFY_API_KEY
        self.base_url = base_url or settings.DIFY_API_BASE_URL
        self.headers = {
            "Content-Type": "application/json"
        }
        # Only add Authorization header if api_key is provided and not empty
        if self.api_key:
             self.headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
    
    async def send_chat_message(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        user: Optional[str] = None,
        inputs: Optional[Dict[str, Any]] = None,
        files: Optional[List[Dict[str, Any]]] = None,
        streaming: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None] | Dict[str, Any]:
        """
        Send a chat message to Dify API
        
        Args:
            query: User input/query
            conversation_id: Optional conversation ID for continuing a conversation
            user: Optional user identifier
            inputs: Optional dictionary of input variables
            files: Optional list of file dictionaries
            streaming: Whether to use streaming response mode
            
        Returns:
            Generator of streaming events or complete response dict
            
        Raises:
            DifyApiException: If there's an error with the Dify API
        """
        try:
            url = f"{self.base_url}/chat-messages"
            
            payload = {
                "query": query,
                "inputs": inputs or {},
                "response_mode": "streaming" if streaming else "blocking",
                "user": user or "anonymous",
            }
            
            if conversation_id:
                payload["conversation_id"] = conversation_id
                
            if files:
                payload["files"] = files
            
            logger.debug(f"Sending chat request to Dify: {json.dumps(payload, default=str)}")
            
            if streaming:
                # Yield from the streaming response generator
                async for event in self._stream_response(url, payload):
                    yield event
            else:
                # Blocking mode - yield the single complete response
                response = await self.client.post(
                    url,
                    json=payload,
                    headers=self.headers
                )

                if response.status_code != 200:
                    self._handle_error_response(response)

                yield response.json() # Yield the single result
                
        except httpx.RequestError as e:
            logger.error(f"Error connecting to Dify API: {str(e)}")
            raise DifyApiException(f"连接 Dify API 时出错: {str(e)}")
    
    async def _stream_response(self, url: str, payload: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream response from Dify API
        
        Args:
            url: API endpoint URL
            payload: Request payload
            
        Returns:
            Async generator of response chunks
            
        Raises:
            DifyApiException: If there's an error with the Dify API
        """
        try:
            async with self.client.stream("POST", url, json=payload, headers=self.headers) as response:
                if response.status_code != 200:
                    # Read the error body asynchronously
                    error_body_bytes = b""
                    async for chunk in response.aiter_bytes():
                        error_body_bytes += chunk
                    error_msg = error_body_bytes # Now we have the full error body bytes

                    try:
                        # Decode before parsing JSON
                        error_data = json.loads(error_msg.decode("utf-8"))
                        detail = error_data.get("message", "Unknown error")
                    except Exception: # Catch broader exceptions during decoding/parsing
                        try:
                            # Try decoding as utf-8 if JSON fails
                            detail = error_msg.decode("utf-8")
                        except UnicodeDecodeError:
                             # Fallback if decoding fails
                            detail = f"Non-decodable error body (status: {response.status_code})"

                    # 保留 Dify 返回的原始 detail
                    raise DifyApiException(
                        f"Dify API 错误: {detail}",
                        status_code=response.status_code
                    )

                # Process the streaming response
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    
                    # Process complete SSE events from buffer
                    while "\n\n" in buffer:
                        event, buffer = buffer.split("\n\n", 1)
                        
                        # Parse the SSE event
                        if event.startswith("data: "):
                            data_str = event[6:]  # Remove "data: " prefix
                            try:
                                data = json.loads(data_str)
                                yield data
                            except json.JSONDecodeError:
                                logger.error(f"Error parsing SSE data: {data_str}")
                                
        except httpx.RequestError as e:
            logger.error(f"Error streaming from Dify API: {str(e)}")
            raise DifyApiException(f"从 Dify API 流式传输时出错: {str(e)}")
    
    async def stop_generation(self, task_id: str, user: str) -> Dict[str, Any]:
        """
        Stop an ongoing generation task
        
        Args:
            task_id: Task ID to stop
            user: User identifier (required by Dify API)
            
        Returns:
            API response
            
        Raises:
            DifyApiException: If there's an error with the Dify API
        """
        try:
            # Corrected URL according to Dify documentation
            url = f"{self.base_url}/chat-messages/{task_id}/stop"
            
            response = await self.client.post(
                url,
                # Added user to the payload
                json={"user": user},
                headers=self.headers
            )
            
            if response.status_code != 200:
                self._handle_error_response(response)
            
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error stopping generation: {str(e)}")
            raise DifyApiException(f"停止生成时出错: {str(e)}")
    
    async def upload_file(self, file: UploadFile, user: str) -> Dict[str, Any]:
        """
        Upload a file to Dify
        
        Args:
            file: File to upload
            user: User identifier (required by Dify API)
            
        Returns:
            Upload response with file ID
            
        Raises:
            DifyApiException: If there's an error with the Dify API
        """
        try:
            # Corrected URL according to Dify documentation
            url = f"{self.base_url}/files/upload"
            
            # Prepare file for upload
            file_content = await file.read()
            files = {"file": (file.filename, file_content, file.content_type)}
            # Prepare data payload including the user
            data = {"user": user}
            
            # Use multipart/form-data for file upload
            headers = {"Authorization": f"Bearer {self.api_key}"} # Content-Type is handled by httpx for multipart
            
            response = await self.client.post(
                url,
                files=files,
                data=data, # Pass user in data part
                headers=headers
            )
            
            if response.status_code != 201:
                self._handle_error_response(response)
            
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error uploading file to Dify: {str(e)}")
            raise DifyApiException(f"上传文件到 Dify 时出错: {str(e)}")
    
    async def get_conversations(
        self,
        user_id: str,
        last_id: Optional[str] = None, # Changed from page to last_id
        limit: int = 20,
        sort_by: Optional[str] = None, # Added sort_by
        start_date: Optional[str] = None, # Kept for potential filtering
        end_date: Optional[str] = None,   # Kept for potential filtering
        keyword: Optional[str] = None     # Kept for potential filtering
    ) -> Dict[str, Any]: # Return the whole response dict to get 'has_more' etc.
        """
        Get conversations from Dify API using last_id pagination.
        
        Args:
            user_id: User ID for filtering conversations
            last_id: Optional ID of the last conversation from the previous page
            limit: Items per page (default 20, max 100)
            sort_by: Optional sorting field (e.g., '-updated_at', 'created_at')
            start_date: Optional start date filter (ISO format) - Note: Check if Dify supports this with last_id
            end_date: Optional end date filter (ISO format) - Note: Check if Dify supports this with last_id
            keyword: Optional keyword search - Note: Check if Dify supports this with last_id
            
        Returns:
            Dictionary containing list of conversation objects and pagination info
            
        Raises:
            DifyApiException: If there's an error with the Dify API
        """
        try:
            url = f"{self.base_url}/conversations"
            
            # Build query parameters using last_id
            params = {
                "user": user_id,
                "limit": min(max(limit, 1), 100), # Ensure limit is within 1-100
            }
            
            if last_id:
                params["last_id"] = last_id
                
            if sort_by:
                params["sort_by"] = sort_by
                
            # Include other filters if needed and supported by Dify with last_id pagination
            if start_date:
                params["start_date"] = start_date
                
            if end_date:
                params["end_date"] = end_date
                
            if keyword:
                params["keyword"] = keyword
            
            response = await self.client.get(
                url,
                params=params,
                headers=self.headers
            )
            
            if response.status_code != 200:
                self._handle_error_response(response)
            
            # Return the full response dictionary
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error fetching conversations from Dify: {str(e)}")
            raise DifyApiException(f"获取对话列表时出错: {str(e)}")

    # TODO: Verify if the 'GET /conversations/{conversation_id}' endpoint exists in the target Dify API version.
    # The provided documentation did not explicitly list this endpoint.
    async def get_conversation(
        self,
        conversation_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get conversation details (Assumes endpoint exists, needs verification)
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID (for access validation)
            
        Returns:
            Conversation details
            
        Raises:
            DifyApiException: If there's an error with the Dify API
        """
        try:
            url = f"{self.base_url}/conversations/{conversation_id}"
            
            response = await self.client.get(
                url,
                params={"user": user_id},
                headers=self.headers
            )
            
            if response.status_code != 200:
                self._handle_error_response(response)
            
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error fetching conversation details from Dify: {str(e)}")
            raise DifyApiException(f"获取对话详情时出错: {str(e)}")
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        user_id: str,
        first_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get messages for a conversation
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID (for access validation)
            first_id: Optional first message ID for pagination
            limit: Maximum number of messages to return
            
        Returns:
            List of messages
            
        Raises:
            DifyApiException: If there's an error with the Dify API
        """
        try:
            # Corrected URL and parameter passing based on user's curl command
            url = f"{self.base_url}/messages"

            # Build query parameters
            params = {
                "user": user_id,
                "limit": limit,
                "conversation_id": conversation_id # conversation_id is a query parameter
            }

            if first_id:
                params["first_id"] = first_id

            logger.debug(f"Sending GET request to Dify API: {url} with params: {params}")
            response = await self.client.get(
                url,
                params=params,
                headers=self.headers
            )
            logger.debug(f"Received response from Dify API with status code: {response.status_code}")

            if response.status_code != 200:
                self._handle_error_response(response)

            data = response.json()
            # Assuming the response structure is still { "data": [...] }
            return data.get("data", [])

        except httpx.RequestError as e:
            logger.error(f"Error fetching messages from Dify: {str(e)}")
            raise DifyApiException(f"获取消息列表时出错: {str(e)}")

    async def feedback_message(
        self,
        message_id: str,
        rating: Optional[str], # 'like', 'dislike', or None to clear
        user: str,
        content: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Provide feedback (like/dislike) for a message.
        
        Args:
            message_id: The ID of the message to provide feedback for.
            rating: 'like', 'dislike', or None to remove feedback.
            user: User identifier.
            content: Optional feedback content/comment.
            
        Returns:
            API response (usually {"result": "success"})
            
        Raises:
            DifyApiException: If there's an error with the Dify API.
        """
        try:
            url = f"{self.base_url}/messages/{message_id}/feedbacks"
            payload = {
                "rating": rating,
                "user": user
            }
            if content:
                payload["content"] = content
                
            response = await self.client.post(url, json=payload, headers=self.headers)
            
            if response.status_code != 200:
                self._handle_error_response(response)
                
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error sending message feedback to Dify: {str(e)}")
            raise DifyApiException(f"发送消息反馈时出错: {str(e)}")

    async def get_suggested_questions(
        self,
        message_id: str,
        user: str
    ) -> Dict[str, Any]:
        """
        Get suggested questions after a message.
        
        Args:
            message_id: The ID of the message to get suggestions for.
            user: User identifier.
            
        Returns:
            API response containing suggested questions.
            
        Raises:
            DifyApiException: If there's an error with the Dify API.
        """
        try:
            url = f"{self.base_url}/messages/{message_id}/suggested"
            params = {"user": user}
            
            response = await self.client.get(url, params=params, headers=self.headers)
            
            if response.status_code != 200:
                self._handle_error_response(response)
                
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error getting suggested questions from Dify: {str(e)}")
            raise DifyApiException(f"获取建议问题时出错: {str(e)}")

    async def rename_conversation(
        self,
        conversation_id: str,
        user: str,
        name: Optional[str] = None,
        auto_generate: bool = False
    ) -> Dict[str, Any]:
        """
        Rename a conversation or trigger auto-generation of the name.
        
        Args:
            conversation_id: The ID of the conversation to rename.
            user: User identifier.
            name: The new name for the conversation. Required if auto_generate is False.
            auto_generate: Whether to auto-generate the name. Defaults to False.
            
        Returns:
            API response with updated conversation details.
            
        Raises:
            DifyApiException: If there's an error with the Dify API.
        """
        if not auto_generate and not name:
            raise ValueError("Either 'name' must be provided or 'auto_generate' must be True.")
            
        try:
            url = f"{self.base_url}/conversations/{conversation_id}/name"
            payload = {
                "user": user,
                "auto_generate": auto_generate
            }
            if name:
                payload["name"] = name
                
            response = await self.client.post(url, json=payload, headers=self.headers)
            
            if response.status_code != 200:
                self._handle_error_response(response)
                
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error renaming conversation in Dify: {str(e)}")
            raise DifyApiException(f"重命名对话时出错: {str(e)}")

    async def delete_conversation(
        self,
        conversation_id: str,
        user: str
    ) -> Dict[str, Any]:
        """
        Delete a conversation.
        
        Args:
            conversation_id: The ID of the conversation to delete.
            user: User identifier.
            
        Returns:
            API response (usually {"result": "success"})
            
        Raises:
            DifyApiException: If there's an error with the Dify API.
        """
        try:
            url = f"{self.base_url}/conversations/{conversation_id}"
            payload = {"user": user}
            
            response = await self.client.delete(url, json=payload, headers=self.headers) # Use DELETE method
            
            # Dify might return 200 OK with {"result": "success"} or potentially 204 No Content
            if response.status_code not in [200, 204]:
                 self._handle_error_response(response)

            # If 204, return a standard success message
            if response.status_code == 204:
                return {"result": "success"}

            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error deleting conversation in Dify: {str(e)}")
            raise DifyApiException(f"删除对话时出错: {str(e)}")

    async def audio_to_text(
        self,
        file: UploadFile,
        user: str
    ) -> Dict[str, Any]:
        """
        Convert audio file to text using Dify.
        
        Args:
            file: Audio file to transcribe.
            user: User identifier.
            
        Returns:
            API response containing the transcribed text.
            
        Raises:
            DifyApiException: If there's an error with the Dify API.
        """
        try:
            url = f"{self.base_url}/audio-to-text"
            
            file_content = await file.read()
            files = {"file": (file.filename, file_content, file.content_type)}
            data = {"user": user}
            
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            response = await self.client.post(url, files=files, data=data, headers=headers)
            
            if response.status_code != 200:
                self._handle_error_response(response)
                
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error converting audio to text via Dify: {str(e)}")
            raise DifyApiException(f"音频转文本时出错: {str(e)}")

    async def text_to_audio(
        self,
        user: str,
        text: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> bytes:
        """
        Convert text to audio using Dify. Returns raw audio bytes.
        
        Args:
            user: User identifier.
            text: Text to convert. Required if message_id is not provided.
            message_id: ID of a Dify message to convert. Takes precedence over text.
            
        Returns:
            Raw audio bytes (e.g., WAV or MP3).
            
        Raises:
            DifyApiException: If there's an error with the Dify API.
            ValueError: If neither text nor message_id is provided.
        """
        if not text and not message_id:
            raise ValueError("Either 'text' or 'message_id' must be provided for text-to-audio.")
            
        try:
            url = f"{self.base_url}/text-to-audio"
            payload = {"user": user}
            if message_id:
                payload["message_id"] = message_id
            elif text:
                payload["text"] = text
                
            # Make the request expecting raw audio data
            response = await self.client.post(url, json=payload, headers=self.headers)
            
            if response.status_code != 200:
                # Try to parse error details if it's JSON, otherwise use raw text
                try:
                    error_data = response.json()
                    detail = error_data.get("message", "Unknown API error")
                except:
                    detail = response.text or f"HTTP Error {response.status_code}"
                
                logger.error(f"Dify API error (text-to-audio): {detail} - Status: {response.status_code}")
                # 保留 Dify 返回的原始 detail
                raise DifyApiException(
                    f"Dify API 错误 (文本转音频): {detail}",
                    status_code=response.status_code
                )
                
            # Return the raw audio content
            return response.content
            
        except httpx.RequestError as e:
            logger.error(f"Error converting text to audio via Dify: {str(e)}")
            raise DifyApiException(f"文本转音频时出错: {str(e)}")
    
    def _handle_error_response(self, response: httpx.Response):
        """
        Handle error response from Dify API
        
        Args:
            response: HTTP response object
            
        Raises:
            DifyApiException: With details from the response
        """
        try:
            # Try parsing JSON error first
            error_data = response.json()
            detail = error_data.get("message", "Unknown API error")
            code = error_data.get("code", "unknown_error")
        except json.JSONDecodeError:
            # If not JSON, use raw text
            detail = response.text or f"HTTP Error {response.status_code}"
            code = "unknown_error"
        except Exception:
             # Fallback for other potential parsing issues
            detail = response.text or f"HTTP Error {response.status_code}"
            code = "unknown_error"

        logger.error(f"Dify API error: {detail} - Status: {response.status_code} - Code: {code}")
        # 保留 Dify 返回的原始 detail
        raise DifyApiException(
            detail=f"Dify API 错误: {detail}",
            status_code=response.status_code,
            code=code
        )

    async def get_app_info(self) -> Dict[str, Any]:
        """
        Get basic application information from Dify using GET /info.
        Uses the service's configured base_url and api_key.
        
        Returns:
            Dictionary containing app name, description, tags, etc.
            
        Raises:
            DifyApiException: If there's an error communicating with the Dify API.
        """
        try:
            url = f"{self.base_url}/info"
            
            # Use the service's headers which include the Authorization token
            response = await self.client.get(url, headers=self.headers)
            
            if response.status_code != 200:
                self._handle_error_response(response)
                
            return response.json()
            
        except httpx.RequestError as e:
            logger.error(f"Error fetching app info from Dify: {str(e)}")
            raise DifyApiException(f"获取应用信息时出错: {str(e)}")

    async def get_app_parameters(self) -> Dict[str, Any]:
        """
        Get application parameters from Dify using GET /parameters.
        Uses the service's configured base_url and api_key.

        Returns:
            Dictionary containing app parameters.

        Raises:
            DifyApiException: If there's an error communicating with the Dify API.
        """
        try:
            url = f"{self.base_url}/parameters"

            # Use the service's headers which include the Authorization token
            response = await self.client.get(url, headers=self.headers)

            if response.status_code != 200:
                self._handle_error_response(response)

            return response.json()

        except httpx.RequestError as e:
            logger.error(f"Error fetching app parameters from Dify: {str(e)}")
            raise DifyApiException(f"获取应用参数时出错: {str(e)}")
