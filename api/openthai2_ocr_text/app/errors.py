from fastapi.responses import JSONResponse


class ServiceError(Exception):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status


def error_response(error, request_id):
    return JSONResponse({"error": {"code": error.code, "message": error.message,
                                  "details": [], "request_id": request_id, "docs": ""}},
                        status_code=error.status,
                        headers={"X-Request-ID": request_id, **({"Retry-After": "5"} if error.status == 429 else {})})
