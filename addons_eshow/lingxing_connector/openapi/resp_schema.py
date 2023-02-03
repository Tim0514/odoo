#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""openapi接口响应 schema"""
from pydantic import BaseModel
from typing import Any, Optional


class ResponseResult(BaseModel):
    code: Optional[int]                     # 响应码
    message: Optional[str]                  # 响应信息
    data: Any                               # 接口响应数据
    error_details: Optional[Any] = None     # 异常信息
    request_id: Optional[str] = None        # 标记本次请求唯一ID
    response_time: Optional[str] = None     # 响应时间
    total: Optional[int] = None


class AccessTokenDto(BaseModel):
    access_token: str           # 接口访问认证信息
    refresh_token: str          # RefreshToken用于续费AccessToken，只能使用一次
    expires_in: int             # AccessToken的有效期, TTL
