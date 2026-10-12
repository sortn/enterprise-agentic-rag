from __future__ import annotations

from fastapi import Request


def get_chat_service(request: Request):
    return request.app.state.services.chat


def get_document_service(request: Request):
    return request.app.state.services.documents


def get_knowledge_base_service(request: Request):
    return request.app.state.services.knowledge_bases


def get_conversation_service(request: Request):
    return request.app.state.services.conversations


def get_audit_service(request: Request):
    return request.app.state.services.audit


def get_evaluation_service(request: Request):
    return request.app.state.services.evaluation
