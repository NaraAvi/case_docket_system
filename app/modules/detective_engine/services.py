"""Backward-compatible detective workflow module."""

from app.modules.procedure_engine.services import DetectiveProcedureService, ProcedureEngineService

__all__ = [
    "DetectiveProcedureService",
    "ProcedureEngineService",
]
