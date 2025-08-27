# 企业微信智能机器人回调服务配置指南

## 概述

本服务实现了企业微信智能机器人的回调处理，支持：
- 文本消息处理
- 图片消息处理和解密
- 流式响应处理
- 与 Dify AI 的集成
- 异步后台任务处理

## 核心架构

### 1. 真实流式处理
- 使用 Dify 的流式 API 替代模拟的分步处理
- 实时接收和处理 AI 响应

### 2. 后台任务机制
- 使用 FastAPI BackgroundTasks 解耦流式接收和回调响应
- 避免企业微信回调超时

### 3. 智能内容解析
- 实时解析 Markdown 图片链接并异步下载处理
- 支持文本和图片混合消息

### 4. 有序消息缓存
- 维护文本和图片的正确显示顺序
- 自动清理过期缓存

### 5. 多媒体支持
- 完整支持图片上传和返回
- 支持加密图片的解密处理

## 环境变量配置

在 `.env` 文件或环境变量中设置以下配置：

```bash
# 企业微信智能机器人配置
WECOM_TOKEN=your_wecom_token_here
WECOM_ENCODING_AES_KEY=your_encoding_aes_key_here
WECOM_RECEIVE_ID=  # 智能机器人通常为空字符串

# aibotid 到 Agent ID 的映射配置 (JSON格式)
# 例如: {"AIBOT001": "1", "AIBOT002": "2"}
WECOM_AIBOT_AGENT_MAPPING={"your_aibotid": "your_agent_id"}

# 默认 Dify API 配置（可选，如果所有 Agent 都有自己的配置）
DIFY_API_BASE_URL=http://your-dify-server/v1
DIFY_API_KEY=your_dify_api_key_here
```

## 企业微信后台配置

### 1. 创建智能机器人
1. 登录企业微信管理后台
2. 前往 "应用管理" -> "第三方" -> "智能机器人"
3. 创建新的智能机器人应用

### 2. 配置回调URL
在智能机器人配置中设置回调URL：
```
https://your-domain.com/wecom/callback/{botid}
```

其中 `{botid}` 是你的机器人ID。

### 3. 获取配置参数
- **Token**: 在机器人配置页面生成
- **EncodingAESKey**: 在机器人配置页面生成
- **ReceiveID**: 智能机器人通常为空字符串

## API 接口

### GET /wecom/callback/{botid}
用于验证回调URL的有效性。

**参数：**
- `botid`: 机器人ID
- `msg_signature`: 消息签名
- `timestamp`: 时间戳
- `nonce`: 随机数
- `echostr`: 验证字符串

### POST /wecom/callback/{botid}
处理企业微信消息回调。

**参数：**
- `botid`: 机器人ID
- `msg_signature`: 消息签名
- `timestamp`: 时间戳
- `nonce`: 随机数

**支持的消息类型：**
- `text`: 文本消息
- `image`: 图片消息
- `stream`: 流式消息续传
- `mixed`: 混合消息（图文混排）
- `event`: 事件消息（待实现）

**新增消息字段：**
- `msgid`: 消息唯一标识（用于去重）
- `aibotid`: 智能机器人ID（映射到具体的 Agent）
- `chatid`: 会话ID（仅群聊时返回）
- `chattype`: 会话类型（single/group）
- `from.userid`: 发送者用户ID

## 流式消息处理流程

1. **接收用户消息**: 企业微信发送用户消息到回调接口
2. **立即响应**: 返回"正在思考中..."的初始流式消息
3. **后台处理**: 启动后台任务调用 Dify API
4. **流式接收**: 实时接收 Dify 的流式响应
5. **内容解析**: 解析响应中的文本和图片链接
6. **图片处理**: 异步下载和处理图片
7. **消息缓存**: 维护消息内容的有序缓存
8. **续传响应**: 企业微信轮询获取最新内容
9. **完成标记**: 标记消息完成并清理缓存

## 图片处理

### 加密图片解密
服务支持企业微信加密图片的自动解密：
1. 下载加密图片数据
2. 使用 EncodingAESKey 进行 AES-CBC 解密
3. 去除 PKCS#7 填充
4. 返回解密后的图片数据

### Markdown 图片链接
AI 响应中的 Markdown 图片链接会被自动解析和下载：
```markdown
![描述](https://example.com/image.jpg)
```

## 错误处理

服务包含完整的错误处理机制：
- 消息解密失败
- Dify API 调用错误
- 图片下载和处理错误
- 网络超时和重试

## 性能优化

- 使用异步 HTTP 客户端
- 后台任务处理避免阻塞
- 自动缓存清理机制
- 合理的超时设置

## 安全考虑

- 消息签名验证
- AES 加密/解密
- 参数验证和清理
- 错误信息不泄露敏感数据

## 部署建议

1. **环境变量**: 使用环境变量管理敏感配置
2. **HTTPS**: 生产环境必须使用 HTTPS
3. **负载均衡**: 支持多实例部署
4. **监控日志**: 配置适当的日志级别和监控

## 故障排除

### 常见问题

1. **URL验证失败**
   - 检查 Token 和 EncodingAESKey 配置
   - 确认回调URL格式正确
   - 查看服务器日志

2. **消息解密失败**
   - 验证 EncodingAESKey 是否正确
   - 检查消息格式

3. **Dify API 调用失败**
   - 验证 DIFY_API_KEY 和 DIFY_API_BASE_URL
   - 检查网络连接

4. **图片处理失败**
   - 检查图片URL可访问性
   - 验证图片格式支持

### 日志查看
服务使用 loguru 进行日志记录，可以通过以下方式查看：
```bash
# 查看应用日志
tail -f logs/app.log

# 查看企业微信相关日志
grep "wecom" logs/app.log
```

## 开发和测试

### 本地开发
```bash
# 安装依赖
uv sync

# 设置环境变量
export WECOM_TOKEN=your_token
export WECOM_ENCODING_AES_KEY=your_key
export DIFY_API_KEY=your_dify_key

# 启动服务
python app/main.py
```

### 测试回调
可以使用 ngrok 等工具在本地测试：
```bash
# 启动 ngrok
ngrok http 15000

# 使用 ngrok 提供的URL配置企业微信回调
```

## 扩展功能

服务设计支持未来扩展：
- 多机器人支持
- 更多消息类型处理
- 用户会话管理
- 消息持久化存储
- 更丰富的 AI 功能集成
