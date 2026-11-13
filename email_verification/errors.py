import uuid

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler


class AuthError(APIException):
    def __init__(self, message, *, status=400, code="VALIDATION_ERROR"):
        self.status_code = status
        self.auth_code = code
        super().__init__(message)


def auth_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        # Never expose request bodies, SQL errors, mail credentials or JWTs.
        response = Response(status=500)
    status = response.status_code
    code = getattr(exc, "auth_code", {
        400: "VALIDATION_ERROR", 401: "AUTHENTICATION_REQUIRED",
        403: "PERMISSION_DENIED", 404: "NOT_FOUND", 405: "INVALID_STATE",
        409: "INVALID_STATE", 429: "RATE_LIMITED", 500: "INTERNAL_SERVER_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }.get(status, "INVALID_STATE"))
    # Serializer messages can include submitted values. Return field names only.
    details = {}
    if status == 400 and isinstance(getattr(exc, "detail", None), dict):
        details = {str(name): ["요청값을 확인해 주세요."] for name in exc.detail}
    message = "요청을 처리할 수 없습니다."
    if isinstance(exc, AuthError):
        message = str(exc.detail)
    elif status == 400:
        message = "요청값을 확인해 주세요."
    elif status == 500:
        message = "서버 내부 오류가 발생했습니다."
    response.data = {
        "code": code, "message": message, "details": details,
        "request_id": "req_" + uuid.uuid4().hex,
    }
    return response
