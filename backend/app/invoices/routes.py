from fastapi import APIRouter

from app.accounting.catalog import get_northstar_gl_catalog
from app.accounting.models import GLAccount

router = APIRouter()


@router.get("/gl-catalog", response_model=list[GLAccount])
def get_gl_catalog() -> list[GLAccount]:
    return list(get_northstar_gl_catalog())
