# Asinking OpenAPI Python3 SDK

python版本: >= 3.8.3
## 基本使用

```python
#!/usr/bin/python3
import asyncio

from openapi import OpenApiBase


async def main():
    op_api = OpenApiBase("host", "appId", "appSecret")
    token_resp = await op_api.generate_access_token()
    # 可以自行将AccessToken保存到缓存中
    print(token_resp.access_token)
    # RefreshToken用于续费AccessToken，只能使用一次
    print(token_resp.refresh_token)
    # AccessToken的有效期，TTL
    print(token_resp.expires_in)

    # # 刷新AccessToken
    # token_resp = await op_api.refresh_token(token_resp.refresh_token)

    # 组装请求参数
    req_body = {
            "data": {
                "title": "华为2",
                "parent_cid": ""
            }
        }
    
    # 发起OpenAPI的请求
    resp = await op_api.request(token_resp.access_token, "/erp/sc/routing/storage/category/set", "POST",
                                req_body=req_body)
    print(resp.dict())
    print(resp.code)
    print(resp.data)
    print(resp.error_details)
    print(resp.request_id)
    print(resp.response_time)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
```

PS: 也可以参见 tests 目录下的 单元测试~

注意: 当参数带有中文或其他特殊字符时, 需要在python文件头添加 utf-8标识, 否则会导致签名异常...