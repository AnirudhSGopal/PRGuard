#!/usr/bin/env python3
"""
SQLite → PostgreSQL Data Migration Script for PRGuard

Usage:
    1. Set up .env with your Neon PostgreSQL connection string
    2. Run: python migrate_sqlite_to_postgres.py
    
This script:
    - Reads data from SQLite (prguard.db)
    - Creates tables in PostgreSQL
    - Migrates all data while preserving relationships
"""

import asyncio
import sqlite3
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.base import Base
from app.models.user import User
from app.models.chat import Message, Session
from app.models.review import Review
from app.models.webhook import WebhookEvent
from app.models.repository import ConnectedRepository


def get_sqlite_connection():
    """Connect to SQLite database."""
    return sqlite3.connect("prguard.db")


async def migrate_data():
    """Main migration function."""
    print("🔄 Starting SQLite → PostgreSQL migration...\n")
    
    # Check that we're actually using PostgreSQL
    if settings.DATABASE_URL.startswith("sqlite"):
        print("❌ ERROR: DATABASE_URL is still SQLite!")
        print("   Please update .env with your Neon PostgreSQL URL first.")
        print("   Example: DATABASE_URL=postgresql+asyncpg://user:pass@host/db")
        return False
    
    print(f"📦 Source: SQLite (prguard.db)")
    print(f"📦 Target: PostgreSQL\n")
    
    # Create PostgreSQL engine
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    
    try:
        # Step 1: Create all tables
        print("1️⃣  Creating database schema in PostgreSQL...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("   ✅ Schema created\n")
        
        # Step 2: Migrate data
        session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        sqlite_conn = get_sqlite_connection()
        sqlite_cursor = sqlite_conn.cursor()
        
        # Migrate Users
        print("2️⃣  Migrating users...")
        sqlite_cursor.execute("SELECT * FROM users")
        users_data = sqlite_cursor.fetchall()
        user_columns = [desc[0] for desc in sqlite_cursor.description]
        
        async with session_factory() as session:
            for row in users_data:
                user_dict = dict(zip(user_columns, row))
                user = User(**user_dict)
                session.add(user)
            await session.commit()
        
        print(f"   ✅ Migrated {len(users_data)} users\n")
        
        # Migrate Sessions
        print("3️⃣  Migrating chat sessions...")
        sqlite_cursor.execute("SELECT * FROM sessions")
        sessions_data = sqlite_cursor.fetchall()
        session_columns = [desc[0] for desc in sqlite_cursor.description]
        
        async with session_factory() as session:
            for row in sessions_data:
                session_dict = dict(zip(session_columns, row))
                chat_session = Session(**session_dict)
                session.add(chat_session)
            await session.commit()
        
        print(f"   ✅ Migrated {len(sessions_data)} sessions\n")
        
        # Migrate Messages
        print("4️⃣  Migrating messages...")
        sqlite_cursor.execute("SELECT * FROM messages")
        messages_data = sqlite_cursor.fetchall()
        message_columns = [desc[0] for desc in sqlite_cursor.description]
        
        async with session_factory() as session:
            for row in messages_data:
                message_dict = dict(zip(message_columns, row))
                message = Message(**message_dict)
                session.add(message)
            await session.commit()
        
        print(f"   ✅ Migrated {len(messages_data)} messages\n")
        
        # Migrate Reviews
        print("5️⃣  Migrating reviews...")
        sqlite_cursor.execute("SELECT * FROM reviews")
        reviews_data = sqlite_cursor.fetchall()
        review_columns = [desc[0] for desc in sqlite_cursor.description]
        
        async with session_factory() as session:
            for row in reviews_data:
                review_dict = dict(zip(review_columns, row))
                review = Review(**review_dict)
                session.add(review)
            await session.commit()
        
        print(f"   ✅ Migrated {len(reviews_data)} reviews\n")
        
        # Migrate Connected Repositories
        print("6️⃣  Migrating connected repositories...")
        sqlite_cursor.execute("SELECT * FROM connected_repositories")
        repos_data = sqlite_cursor.fetchall()
        repo_columns = [desc[0] for desc in sqlite_cursor.description]
        
        async with session_factory() as session:
            for row in repos_data:
                repo_dict = dict(zip(repo_columns, row))
                repo = ConnectedRepository(**repo_dict)
                session.add(repo)
            await session.commit()
        
        print(f"   ✅ Migrated {len(repos_data)} repositories\n")
        
        # Migrate Webhook Events
        print("7️⃣  Migrating webhook events...")
        sqlite_cursor.execute("SELECT * FROM webhook_events")
        webhooks_data = sqlite_cursor.fetchall()
        webhook_columns = [desc[0] for desc in sqlite_cursor.description]
        
        async with session_factory() as session:
            for row in webhooks_data:
                webhook_dict = dict(zip(webhook_columns, row))
                webhook = WebhookEvent(**webhook_dict)
                session.add(webhook)
            await session.commit()
        
        print(f"   ✅ Migrated {len(webhooks_data)} webhook events\n")
        
        sqlite_conn.close()
        
        # Final verification
        print("8️⃣  Verifying migration...")
        async with session_factory() as session:
            from sqlalchemy import func
            user_count = await session.scalar(func.count(User.id))
            session_count = await session.scalar(func.count(Session.id))
            msg_count = await session.scalar(func.count(Message.id))
            
        print(f"   ✅ Verification complete:")
        print(f"      • Users: {user_count}")
        print(f"      • Sessions: {session_count}")
        print(f"      • Messages: {msg_count}\n")
        
        await engine.dispose()
        
        print("✅ Migration complete!\n")
        print("📝 Next steps:")
        print("   1. Restart your backend: python run.py")
        print("   2. Your application now uses PostgreSQL")
        print("   3. Keep prguard.db as backup (can be deleted later)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(migrate_data())
    exit(0 if success else 1)
