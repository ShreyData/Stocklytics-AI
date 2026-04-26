"""
common package – shared utilities for Stocklytics AI backend.

Public surface:
    config          – application settings
    logging_config  – JSON log setup and request_id context var
    middleware      – RequestIdMiddleware
    exceptions      – AppError hierarchy + register_exception_handlers
    auth            – require_auth / require_admin dependencies
    responses       – success_response helper
"""
