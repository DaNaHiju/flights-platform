"""Top deals API router.

Always served from Redis. This router never calls fli directly — the
deals:top cache is populated out-of-band by the refresh job (see
app/jobs/refresh_deals.py), invoked on a schedule by a CronJob defined in
the manifests repo.
"""

from fastapi import APIRouter, HTTPException, Query, status

from shared.cache import get_json

router = APIRouter()

DEALS_CACHE_KEY = "deals:top"


@router.get("")
def list_deals(limit: int = Query(default=10, ge=1, le=50)):
    """Return the top cached deals, cheapest first."""
    cached = get_json(DEALS_CACHE_KEY)
    if cached is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "deals_not_available"},
        )

    return {
        "deals": cached["deals"][:limit],
        "refreshed_at": cached["refreshed_at"],
    }
