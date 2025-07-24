from guard.models import SecurityConfig
from guard.decorators import SecurityDecorator

# 1. 在此集中定义您的 SecurityConfig
# 请根据您的实际情况替换 "127.0.0.1" 为您信任的反向代理服务器 IP 地址。
# 您可以使用 CIDR 表示法，例如 "192.168.1.0/24"。
security_config = SecurityConfig(
    enable_redis=False,
    trusted_proxies=["127.0.0.1"],
    rate_limit=100,
)

# 2. 创建一个将在整个应用中共享的 SecurityDecorator 实例
# 所有路由文件都应该导入并使用这个 `guard_deco` 实例。
guard_deco = SecurityDecorator(security_config) 