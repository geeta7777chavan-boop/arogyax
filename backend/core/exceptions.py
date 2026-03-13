"""
core/exceptions.py
==================
Custom application exceptions — keeps routers clean.
"""

from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, resource: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found.",
        )


class OutOfStockError(HTTPException):
    def __init__(self, medicine: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{medicine}' is currently out of stock.",
        )


class PrescriptionRequiredError(HTTPException):
    def __init__(self, medicine: str):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"'{medicine}' requires a valid prescription. Please upload it.",
        )


class AgentError(HTTPException):
    def __init__(self, detail: str = "Agent pipeline failed."):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        )
