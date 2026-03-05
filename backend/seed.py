"""
Seed script: creates initial platform admin and a demo workspace.
Run once after first startup:
  docker compose exec backend python seed.py
"""
import asyncio
from app.core.database import AsyncSessionLocal
from app.services.user_service import UserService
from app.services.workspace_service import WorkspaceService
from app.schemas.user import UserCreate
from app.schemas.workspace import WorkspaceCreate

async def seed():
    async with AsyncSessionLocal() as db:
        # Create platform admin
        try:
            admin = await UserService.create(db, UserCreate(
                email="admin@digitalmind.com.vc",
                full_name="Admin Digital Mind",
                password="changeme123",
                is_platform_admin=True,
            ))
            print(f"✓ Admin criado: {admin.email}")
        except Exception as e:
            print(f"Admin já existe ou erro: {e}")

        # Create demo workspace
        try:
            ws = await WorkspaceService.create(db, WorkspaceCreate(
                name="Demo Client",
                slug="demo-client",
                description="Workspace de demonstração",
                industry="Tecnologia",
                company_size="500-1000",
                contact_email="demo@example.com",
            ))
            await db.commit()
            print(f"✓ Workspace criado: {ws.slug}")
        except Exception as e:
            print(f"Workspace já existe ou erro: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(seed())
