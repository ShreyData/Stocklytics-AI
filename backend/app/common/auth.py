"""
Firebase Auth dependency for FastAPI.

Usage in a protected router:
    from app.common.auth import require_auth, AuthenticatedUser

    @router.get("/resource")
    async def get_resource(user: AuthenticatedUser = Depends(require_auth)):
        store_id = user.store_id
        ...

In local/test environments where FIREBASE_PROJECT_ID is not set, the dependency
can be bypassed using a stub token so the team can develop without live Firebase.
"""

import logging
from dataclasses import dataclass

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.common.config import get_settings
from app.common.exceptions import UnauthorizedError, ForbiddenError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Firebase Admin SDK initialisation (singleton)
# ---------------------------------------------------------------------------

_firebase_initialised = False


def _init_firebase() -> None:
    """Initialise the Firebase Admin SDK once at first use."""
    global _firebase_initialised
    if _firebase_initialised:
        return

    settings = get_settings()

    if not settings.firebase_project_id:
        logger.warning(
            "FIREBASE_PROJECT_ID is not set. "
            "Auth verification will use stub mode (local/dev only)."
        )
        _firebase_initialised = True
        return

    if not firebase_admin._apps:
        if settings.firebase_client_email and settings.firebase_private_key:
            cred = credentials.Certificate(
                {
                    "type": "service_account",
                    "project_id": settings.firebase_project_id,
                    "client_email": settings.firebase_client_email,
                    "private_key": settings.firebase_private_key.replace("\\n", "\n"),
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            )
            firebase_admin.initialize_app(cred)
        else:
            # On Cloud Run, prefer Application Default Credentials from the attached service account.
            firebase_admin.initialize_app(options={"projectId": settings.firebase_project_id})

    _firebase_initialised = True


# ---------------------------------------------------------------------------
# Authenticated user model
# ---------------------------------------------------------------------------

@dataclass
class AuthenticatedUser:
    """
    Represents an authenticated user extracted from a verified Firebase token.

    Attributes:
        user_id:  Firebase UID.
        role:     'admin' | 'staff' (stored as a custom claim on the token).
        store_id: The store this user belongs to (custom claim).
        email:    User email address (optional).
    """
    user_id: str
    role: str
    store_id: str
    email: str | None = None


# ---------------------------------------------------------------------------
# Security scheme
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency that validates the Firebase Bearer token.

    - Raises UnauthorizedError (401) if no token or token is invalid.
    - Raises ForbiddenError (403) if the token lacks required custom claims.
    - Returns AuthenticatedUser on success.

    Stub mode (no FIREBASE_PROJECT_ID set):
        Accepts the literal token 'dev-token' and returns a fake admin user.
        This allows local development without a real Firebase project.
    """
    _init_firebase()
    settings = get_settings()

    if settings.demo_auth_bypass_enabled:
        logger.warning(
            "Demo auth bypass is enabled. Returning a shared demo user for all requests."
        )
        return AuthenticatedUser(
            user_id="demo_user_public",
            role="admin",
            store_id="Demo_Shop",
            email="demo@stocklytics.local",
        )

    if credentials is None:
        raise UnauthorizedError("Missing Authorization header with Bearer token.")

    token = credentials.credentials

    # ---- Stub mode for local development ----
    if not settings.firebase_project_id:
        if token == "dev-token":
            logger.warning(
                "Auth stub mode active: accepting 'dev-token'. "
                "Do not use this in production."
            )
            return AuthenticatedUser(
                user_id="dev_user_001",
                role="admin",
                store_id="Demo_Shop",
                email="dev@stocklytics.local",
            )
        raise UnauthorizedError(
            "Stub auth mode is active. Use the token 'dev-token' for local development."
        )

    # ---- Production Firebase verification ----
    try:
        decoded_token: dict = firebase_auth.verify_id_token(token)
    except firebase_auth.ExpiredIdTokenError:
        raise UnauthorizedError("Token has expired. Please sign in again.")
    except firebase_auth.InvalidIdTokenError:
        raise UnauthorizedError("Token is invalid.")
    except Exception as exc:
        logger.error("Unexpected Firebase auth error", exc_info=exc)
        raise UnauthorizedError("Could not verify authentication token.")

    user_id: str = decoded_token.get("uid", "")
    role: str = decoded_token.get("role", "")
    store_id: str = decoded_token.get("store_id", "")

    if not role or not store_id:
        raise ForbiddenError(
            "Token is missing required claims: 'role' and 'store_id'. "
            "Ensure the user has been assigned a store and role by an admin."
        )

    return AuthenticatedUser(
        user_id=user_id,
        role=role,
        store_id=store_id,
        email=decoded_token.get("email"),
    )


async def require_admin(
    user: AuthenticatedUser = Depends(require_auth),
) -> AuthenticatedUser:
    """
    Dependency that additionally enforces the 'admin' role.
    Use this for admin-only endpoints (e.g., pipeline triggers).
    """
    if user.role != "admin":
        raise ForbiddenError(
            "This action requires admin role.",
            details={"required_role": "admin", "actual_role": user.role},
        )
    return user
