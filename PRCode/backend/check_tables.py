
import asyncio
from app.models.base import engine
from sqlalchemy import text

async def check():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = [row[0] for row in result.fetchall()]
        print(f"Tables in 'public' schema: {tables}")

if __name__ == "__main__":
    asyncio.run(check())
