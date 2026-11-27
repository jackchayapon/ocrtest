from fastapi.responses import JSONResponse


class ServiceError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def error_response(error, request_id):
    headers = {"Retry-After": "5"} if error.status == 429 else {}
    return JSONResponse(
        {
            "error": {"code": error.code, "message": error.message},
            "meta": {"request_id": request_id, "api_version": "v1"},
        },
        status_code=error.status,
        headers=headers,
    )
