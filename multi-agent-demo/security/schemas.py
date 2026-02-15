"""Pydantic schemas for strict validation of every agent output."""

from pydantic import BaseModel, RootModel


class PlannerOutput(BaseModel):
    spec: str
    pages: list[str]
    endpoints: list[str]
    data_models: list[str]


class FEExecutorOutput(RootModel[dict[str, str]]):
    """Filename → code mapping for frontend artifacts."""
    pass


class BEExecutorOutput(RootModel[dict[str, str]]):
    """Filename → code mapping for backend artifacts."""
    pass


class ValidatorOutput(BaseModel):
    passed: bool
    report: str
    target: str = ""
