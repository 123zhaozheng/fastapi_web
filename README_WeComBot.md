# 企业微信智能机器人回调服务

## 快速开始

### 1. 安装依赖

```bash
# 使用 uv 安装依赖（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 2. 环境配置

创建 `.env` 文件并配置以下环境变量：

```bash
# 企业微信智能机器人配置
WECOM_TOKEN=your_wecom_token_here
WECOM_ENCODING_AES_KEY=your_encoding_aes_key_here
WECOM_RECEIVE_ID=  # 智能机器人通常为空字符串

# aibotid 到 Agent ID 的映射配置 (JSON格式)
WECOM_AIBOT_AGENT_MAPPING={"your_aibotid": "your_agent_id"}

# 默认 Dify API 配置（可选）
DIFY_API_BASE_URL=http://your-dify-server/v1
DIFY_API_KEY=your_dify_api_key_here

# 数据库配置（如果需要）
PGHOST=your_db_host
PGPORT=5432
PGUSER=your_db_user
PGPASSWORD=your_db_password
PGDATABASE=your_db_name
```

### 3. 启动服务

```bash
python app/main.py
```

服务将在 `http://localhost:15000` 启动。

### 4. 配置企业微信回调

在企业微信管理后台配置回调URL：
```
https://your-domain.com/wecom/callback/{botid}
```

## 核心功能

✅ **已实现的功能：**
- 企业微信回调URL验证
- 消息加密/解密处理
- 文本消息处理
- 图片消息处理和解密
- **混合消息（图文混排）处理**
- 流式消息响应
- **消息去重机制（基于 msgid）**
- **aibotid 到 Agent 的映射机制**
- **动态 Dify 服务实例创建**
- Dify AI 集成
- 后台异步任务处理
- 智能内容解析（Markdown图片链接）
- 消息缓存管理

🔄 **待扩展功能：**
- 事件消息（event）处理
- 用户会话管理
- 消息持久化存储
- 更丰富的 Agent 权限控制

## 架构特点

- **真实流式处理**: 使用 Dify 流式 API，避免模拟分步处理
- **后台任务机制**: 使用 FastAPI BackgroundTasks 解耦响应
- **智能内容解析**: 自动解析和处理 Markdown 图片链接
- **有序消息缓存**: 维护文本和图片的正确显示顺序
- **多媒体支持**: 完整的图片上传、下载和解密功能

## API 接口

### 验证回调URL
```
GET /wecom/callback/{botid}?msg_signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx
```

### 处理消息回调
```
POST /wecom/callback/{botid}?msg_signature=xxx&timestamp=xxx&nonce=xxx
```

## 消息流程

1. **用户发送消息** → 企业微信 → 回调接口
2. **立即响应** "正在思考中..." → 企业微信
3. **后台处理** 调用 Dify API 获取 AI 响应
4. **流式接收** 实时处理 AI 响应内容
5. **内容解析** 提取文本和图片链接
6. **图片处理** 异步下载和处理图片
7. **续传响应** 企业微信轮询获取完整内容

## 开发说明

项目结构：
```
app/
├── api/
│   └── wecom.py              # 企业微信回调接口
├── utils/
│   ├── ierror.py             # 错误码定义
│   ├── wecom_crypto.py       # 消息加密/解密
│   └── wecom_message.py      # 消息处理工具
├── services/
│   └── dify.py              # Dify API 集成
└── config.py                # 配置管理
```

关键类和函数：
- `WXBizJsonMsgCrypt`: 企业微信消息加解密
- `StreamMessageCache`: 流式消息缓存管理
- `DifyService`: Dify API 服务集成
- `process_dify_response`: 后台任务处理函数

## 部署建议

1. **生产环境**: 使用 HTTPS 和正确的域名
2. **负载均衡**: 支持多实例部署
3. **监控日志**: 配置日志级别和文件输出
4. **安全配置**: 保护敏感环境变量

详细配置指南请参考：[docs/wecom_bot_setup.md](docs/wecom_bot_setup.md)
