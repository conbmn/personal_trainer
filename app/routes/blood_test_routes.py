"""
Blood test API endpoints.

GET  /api/blood-tests         — sync new PDFs then return all stored tests
POST /api/blood-tests/refresh — same, returns counts (useful for explicit UI refresh)
"""

from fastapi import APIRouter

from app.blood_test_store import load_tests, sync_new_pdfs

router = APIRouter(prefix="/api", tags=["blood-tests"])


@router.get("/blood-tests")
async def get_blood_tests():
    await sync_new_pdfs()
    return {"tests": load_tests()}


@router.post("/blood-tests/refresh")
async def refresh_blood_tests():
    added = await sync_new_pdfs()
    tests = load_tests()
    return {"added": added, "total": len(tests)}
