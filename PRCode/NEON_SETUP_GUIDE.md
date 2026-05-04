# Neon PostgreSQL Setup Guide

This guide helps you migrate PRGuard from SQLite to Neon PostgreSQL for production.

## Step 1: Create Neon Account & Database

### 1.1 Sign up / Log in
- Visit: https://console.neon.tech
- Sign up with GitHub or Email
- Create a new project (name: `prguard`)

### 1.2 Get Your Connection String
After creating the project:
1. Go to **Connection string** tab
2. Select **Pooled connection** (recommended for serverless)
3. Choose **Nodejs** driver (uses PostgreSQL driver)
4. Copy the connection string that looks like:
   ```
   postgresql://user:password@host.neon.tech/dbname?sslmode=require
   ```

## Step 2: Update Environment Variables

### 2.1 Update `.env` in backend folder

Replace your current `DATABASE_URL` with the Neon connection string:

**Before (SQLite):**
```env
DATABASE_URL=sqlite+aiosqlite:///./prguard.db
```

**After (Neon PostgreSQL):**
```env
DATABASE_URL=postgresql+asyncpg://user:password@host.neon.tech/dbname?sslmode=require
```

Make sure to:
- Replace `user`, `password`, `host`, `dbname` with your Neon credentials
- Keep the `postgresql+asyncpg://` prefix (Python uses asyncpg driver)
- Include `?sslmode=require` at the end

### 2.2 Example `.env` (after update)
```env
GITHUB_APP_ID=
GITHUB_WEBHOOK_SECRET=
GITHUB_CLIENT_ID=Ov23liMZ79eOs4RrHY9n
GITHUB_CLIENT_SECRET=7a4a33ae3da15763811557ac06c6068410611a46
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=AIzaSyCQ3upTKHGc4dLjvfGAcCUMr4NPJ3aUOoA
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql+asyncpg://user:password@host.neon.tech/prguard?sslmode=require
FRONTEND_URL=http://localhost:5175
APP_URL=http://localhost:8000
ENVIRONMENT=production
SECRET_KEY=your-secret-key-here
ADMIN_USERNAME=anirudhs23
ADMIN_PASSWORD=prguard-admin-2026
```

## Step 3: Migrate Data from SQLite

### 3.1 Run Migration Script

Open terminal in `backend/` folder:

```bash
cd backend
# Activate virtual environment (if not already)
# Windows:
.\.venv\Scripts\Activate.ps1

# Run migration
python migrate_sqlite_to_postgres.py
```

The script will:
- ✅ Create tables in PostgreSQL
- ✅ Migrate all users, sessions, messages, reviews, etc.
- ✅ Verify data integrity

### 3.2 Expected Output
```
🔄 Starting SQLite → PostgreSQL migration...

📦 Source: SQLite (prguard.db)
📦 Target: PostgreSQL

1️⃣  Creating database schema in PostgreSQL...
   ✅ Schema created

2️⃣  Migrating users...
   ✅ Migrated 2 users

3️⃣  Migrating chat sessions...
   ✅ Migrated 15 sessions

... (continues for each table)

✅ Migration complete!
```

## Step 4: Restart Backend with PostgreSQL

### 4.1 Stop Current Backend
Press `CTRL+C` in your terminal running the backend

### 4.2 Start Backend with New Database

```bash
cd backend
python run.py
```

You should see:
```
[STARTUP] Starting PRGuard backend...
[STARTUP] Initializing database...
[STARTUP] Database initialization complete.
```

### 4.3 Test Connection

```bash
curl http://localhost:8000/health
```

Response should show:
```json
{
  "status": "ok",
  "service": "PRGuard",
  "database_url_configured": true,
  "llm_key_configured": true,
  "env_loaded": true
}
```

## Step 5: Verify Everything Works

### 5.1 Admin Dashboard
- Visit: http://localhost:5175/admin/login
- Login with:
  - Username: `anirudhs23`
  - Password: `prguard-admin-2026`
- Should see 2 users (anirudhs23, AnirudhSGopal)

### 5.2 User Dashboard
- Test regular user login
- Create a new chat session
- Verify messages are saved to PostgreSQL

### 5.3 Database Size
Check on Neon console how much data is stored:
- https://console.neon.tech → Your Project → Database → Storage

## Troubleshooting

### Connection Error: "could not connect to server"
- Verify connection string is correct
- Check Neon dashboard for active database
- Ensure your IP is allowed (Neon allows all IPs by default)

### Migration Error: "relations do not exist"
- Backend crashed during migration
- Delete created tables in Neon and retry migration script

### Slow Queries After Migration
- Run: `ALTER TABLE users CREATE INDEX idx_username ON users(username);`
- Add indexes as needed for your queries

## Cleanup

### Keep SQLite Backup
After verifying everything works:
```bash
# Create backup
cp prguard.db prguard-backup.db

# Optionally delete (keep backup first!)
# rm prguard.db
```

## Production Deployment

When deploying to production:

1. **Environment Variables** in your hosting platform (Render, Railway, Heroku, etc.):
   ```
   DATABASE_URL=postgresql+asyncpg://user:pass@host/db?sslmode=require
   ENVIRONMENT=production
   DEBUG=false
   ```

2. **Backend URL** (for frontend CORS):
   ```
   APP_URL=https://your-domain.com
   FRONTEND_URL=https://your-domain.com
   ```

3. **SSL/TLS Certificates**:
   - Neon handles SSL (sslmode=require already included)
   - Frontend should use HTTPS

4. **Database Backups**:
   - Neon includes automated backups
   - Configure retention in Neon dashboard

## Support

- Neon Docs: https://neon.tech/docs
- PRGuard Issues: Check backend logs for database-related errors
- PostgreSQL Issues: Consult PostgreSQL documentation

---

That's it! Your PRGuard backend is now using PostgreSQL. 🎉
