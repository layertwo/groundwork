from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.dependencies.auth import get_current_admin, get_current_user
from backend.exceptions import ConflictError, NotFoundError
from backend.models.role_template import RoleTemplate
from backend.models.user import User
from backend.schemas.role_template import (
    RoleTemplateCreate,
    RoleTemplateResponse,
    RoleTemplateUpdate,
)

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("")
async def list_roles() -> Response:
    return Response(
        status_code=501,
        content='{"detail":"Not implemented"}',
        media_type="application/json",
    )


@router.post("/assume")
async def assume_role() -> Response:
    return Response(
        status_code=501,
        content='{"detail":"Not implemented"}',
        media_type="application/json",
    )


@router.get("/templates", response_model=list[RoleTemplateResponse])
async def list_templates(
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    result = await db.execute(select(RoleTemplate).order_by(RoleTemplate.name))
    return result.scalars().all()


@router.post("/templates", response_model=RoleTemplateResponse, status_code=201)
async def create_template(
    body: RoleTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    existing = await db.execute(select(RoleTemplate).where(RoleTemplate.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"Template '{body.name}' already exists")

    template = RoleTemplate(
        name=body.name,
        description=body.description,
        managed_policy_arns=body.managed_policy_arns,
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=RoleTemplateResponse)
async def update_template(
    template_id: UUID,
    body: RoleTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(RoleTemplate).where(RoleTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("Template not found")

    _UPDATABLE = {"name", "description", "managed_policy_arns"}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in _UPDATABLE:
            setattr(template, field, value)

    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    result = await db.execute(select(RoleTemplate).where(RoleTemplate.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError("Template not found")

    await db.delete(template)
