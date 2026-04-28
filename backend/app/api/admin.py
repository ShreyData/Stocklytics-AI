from fastapi import APIRouter, Depends
from pydantic import BaseModel
from firebase_admin import auth as firebase_auth

from app.common.auth import AuthenticatedUser, require_admin
from app.common.responses import success_response
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

class UpdateStoreRequest(BaseModel):
    store_id: str

@router.post("/users/{uid}/store", summary="Update user's store_id claim")
async def update_user_store(
    uid: str,
    request: UpdateStoreRequest,
    admin: AuthenticatedUser = Depends(require_admin),
):
    """
    Production-ready endpoint to update a user's store_id custom claim.
    Requires the caller to be an admin.
    """
    logger.info(f"Admin {admin.user_id} updating store_id for user {uid} to {request.store_id}")
    
    # 1. Fetch current user from Firebase
    try:
        user_record = firebase_auth.get_user(uid)
    except firebase_auth.UserNotFoundError:
        from app.common.exceptions import NotFoundError
        raise NotFoundError(f"User {uid} not found in Firebase.")
    except Exception as e:
        from app.common.exceptions import InternalServerError
        logger.error(f"Error fetching user: {e}")
        raise InternalServerError("Failed to fetch user from Firebase Auth.")

    # 2. Merge existing claims with new store_id
    claims = user_record.custom_claims or {}
    claims["store_id"] = request.store_id
    
    # 3. Save claims back to Firebase
    try:
        firebase_auth.set_custom_user_claims(uid, claims)
    except Exception as e:
        from app.common.exceptions import InternalServerError
        logger.error(f"Error setting claims: {e}")
        raise InternalServerError("Failed to update user claims in Firebase Auth.")

    return success_response({"message": f"Successfully updated store_id to {request.store_id} for user {uid}. User must re-login to see changes."})
