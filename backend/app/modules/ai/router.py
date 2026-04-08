"""
AI Module router stub.

Owned by: AI Module developer.
Base path: /api/v1/ai

Planned endpoints (implement per ai_implementation.md):
    POST  /api/v1/ai/chat
    GET   /api/v1/ai/chat/sessions/{chat_session_id}

Key rules:
    - AI context must come only from: analytics summary, alerts, inventory snapshot.
    - No vector database, no heavy RAG.
    - AI responses must be grounded in available system data.
    - If analytics data is stale, the response must clearly mention it.
"""

from fastapi import APIRouter

router = APIRouter()

# TODO: implement AI endpoints per ai_implementation.md and api_contracts.md
