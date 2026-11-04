"""Profile and version endpoints (contracts/rest-api.md, "Profile")."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from hiretitan.platform.web.problems import ProblemError
from hiretitan.profile.api.resumes import ProfileApiDeps
from hiretitan.profile.api.schemas import ProfileContentModel
from hiretitan.profile.application.reviews import check_confirm
from hiretitan.profile.application.versions import manual_creator
from hiretitan.profile.infra.repos import ResumeFilesRepo, Version, VersionsRepo


class VersionOut(BaseModel):
    id: UUID
    number: int
    created_at: datetime
    created_by: str
    source_file_name: str | None
    source_deleted: bool
    is_current: bool


class VersionDetailOut(VersionOut):
    content: ProfileContentModel


class ProfileOut(BaseModel):
    current: VersionDetailOut | None


def create_profile_router(deps: ProfileApiDeps) -> APIRouter:
    router = APIRouter(prefix="/profile", tags=["profile"])

    async def describe(version: Version, current_id: UUID | None, session: object) -> VersionOut:
        name = None
        if version.source_file_id is not None:
            file = await ResumeFilesRepo(session).get(version.source_file_id)  # type: ignore[arg-type]
            name = file.original_name if file else None
        return VersionOut(
            id=version.id,
            number=version.number,
            created_at=version.created_at,
            created_by=version.created_by,
            source_file_name=name,
            source_deleted=version.source_deleted,
            is_current=version.id == current_id,
        )

    async def detail(
        version: Version, current_id: UUID | None, session: object
    ) -> VersionDetailOut:
        base = await describe(version, current_id, session)
        return VersionDetailOut(
            **base.model_dump(), content=ProfileContentModel.from_domain(version.content)
        )

    @router.get("")
    async def get_profile() -> ProfileOut:
        async with deps.sessions() as session:
            current = await VersionsRepo(session).current()
            if current is None:
                return ProfileOut(current=None)
            return ProfileOut(current=await detail(current, current.id, session))

    @router.post("/versions", status_code=201)
    async def create_version(body: ProfileContentModel) -> VersionOut:
        content = body.to_domain()
        check = check_confirm(content)
        if not check.ok:
            raise ProblemError(
                422,
                "This profile cannot be saved yet.",
                errors=[{"field": e.path, "message": e.message} for e in check.errors],
            )
        async with deps.sessions() as session:
            versions = VersionsRepo(session)
            creator = manual_creator(await versions.current() is not None)
            version = await versions.create_version(content, created_by=creator)
            out = await describe(version, version.id, session)
            await session.commit()
        return out

    @router.get("/versions")
    async def list_versions() -> list[VersionOut]:
        async with deps.sessions() as session:
            versions = VersionsRepo(session)
            current = await versions.current()
            current_id = current.id if current else None
            return [await describe(v, current_id, session) for v in await versions.list_versions()]

    @router.get("/versions/{version_id}")
    async def get_version(version_id: UUID) -> VersionDetailOut:
        async with deps.sessions() as session:
            versions = VersionsRepo(session)
            version = await versions.get(version_id)
            if version is None:
                raise ProblemError(404, f"Version {version_id} was not found.")
            current = await versions.current()
            return await detail(version, current.id if current else None, session)

    return router
