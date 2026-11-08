"""错误码与业务异常。错误码段：10xxx 参数、20xxx 认证、21xxx 权限、30xxx 业务、50xxx 系统。"""

from __future__ import annotations

from enum import Enum


class ErrorCode(Enum):
    BAD_REQUEST = (10000, "请求参数错误", 400)
    VALIDATION_FAILED = (10001, "参数校验失败", 400)
    FILE_TOO_LARGE = (10002, "文件超过大小上限", 413)
    FILE_TYPE_UNSUPPORTED = (10003, "不支持的文件格式", 400)

    UNAUTHENTICATED = (20001, "未登录或登录已过期", 401)
    TOKEN_INVALID = (20002, "访问令牌无效", 401)

    NO_PERMISSION = (21001, "无此功能权限", 403)
    NO_KB_PERMISSION = (21002, "无此知识库权限", 403)
    NO_ACCESSIBLE_KNOWLEDGE = (21003, "没有可访问的知识库", 403)
    OUT_OF_SCENIC_SCOPE = (21004, "超出景区范围", 403)
    SECURITY_LEVEL_EXCEEDED = (21005, "超出可访问密级", 403)

    NOT_FOUND = (30001, "数据不存在", 404)
    CONFLICT = (30002, "数据状态冲突", 409)
    DUPLICATE_FILE = (30003, "文件已存在", 409)
    INVALID_STATE = (30004, "当前状态不允许该操作", 409)

    INTERNAL = (50000, "系统内部错误", 500)
    PDS_UNAVAILABLE = (50001, "统一权限服务暂不可用", 503)
    DEPENDENCY_FAILED = (50002, "依赖服务调用失败", 502)
    NOT_IMPLEMENTED = (50003, "功能建设中", 501)

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]

    @property
    def http_status(self) -> int:
        return self.value[2]


class BizError(Exception):
    def __init__(self, error: ErrorCode, message: str | None = None, data: object | None = None):
        super().__init__(message or error.message)
        self.error = error
        self.message = message or error.message
        self.data = data


def not_found(what: str) -> BizError:
    return BizError(ErrorCode.NOT_FOUND, f"{what}不存在")
