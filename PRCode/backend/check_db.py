import asyncio
from app.models.base import AsyncSessionLocal
from app.models.working_on import WorkingOnIssue
from sqlalchemy import select

async def check_working_on():
    async with AsyncSessionLocal() as session:
        stmt = select(WorkingOnIssue)
        result = await session.execute(stmt)
        issues = result.scalars().all()
        print(f"Total working on issues: {len(issues)}")
        for issue in issues:
            print(f"User: {issue.user_id}, Repo: {issue.repo_name}, Issue: #{issue.issue_number}, Active: {issue.active}")

if __name__ == "__main__":
    asyncio.run(check_working_on())
