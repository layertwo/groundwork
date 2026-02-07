from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class GroundworkError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(GroundworkError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class ConflictError(GroundworkError):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409)


class ForbiddenError(GroundworkError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status_code=403)


class NotImplementedError(GroundworkError):
    def __init__(self, message: str = "Not implemented"):
        super().__init__(message, status_code=501)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(GroundworkError)
    async def groundwork_error_handler(request: Request, exc: GroundworkError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )
