# Supabase PostgreSQL Setup Guide

This guide helps you set up PRGuard with Supabase PostgreSQL for production.

## Step 1: Create Supabase Account & Database

### 1.1 Sign up / Log in
- Visit: https://supabase.com/dashboard
- Sign up with GitHub or Email
- Create a new project (name: `prguard`, choose a region close to your Render deployment)

### 1.2 Get Your Connection String
After creating the project:
1. Go to **Project Settings → Database**
2. Click **Connection string** tab
3. Select **Transaction pooler** (port 6543 — recommended for serverless/ephemeral connections)
4. Copy the connection string. It looks like:
   ```
   postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
   ```

> **Important**: Use port `6543` (transaction mode), NOT port `5432` (session mode).
> Transaction mode is required for serverless deployments and connection pooling.

### 1.3 Note Your Project Ref
Your project ref is the string after `postgres.` in the username. For example:
```
postgresql://postgres.abcdefghijklmnop:password@...
                      ^^^^^^^^^^^^^^^^
                      This is your project ref
```
You can also find it in **Project Settings → General → Reference ID**.

## Step 2: Update Environment Variables

### 2.1 Update `.env` in the project root

Replace your current `DATABASE_URL` with the Supabase connection string:

**Before (SQLite):**
```env
DATABASE_URL=sqlite+aiosqlite:///./prguard.db
```

**After (Supabase PostgreSQL):**
```env
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

Make sure to:
- Replace `<project-ref>`, `<password>`, and `<region>` with your actual Supabase credentials
- Keep the `postgresql://` prefix (the backend auto-converts to `postgresql+asyncpg://`)
- Include `?sslmode=require` at the end (the backend auto-normalizes this to `?ssl=require` for asyncpg)
- Use port `6543` (transaction pooler)

### 2.2 Example `.env` (after update)
```env
GITHUB_CLIENT_ID=Ov23li...
GITHUB_CLIENT_SECRET=...
GEMINI_API_KEY=AIza...
DATABASE_URL=postgresql://postgres.abcdefghijklmnop:mypassword@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require
FRONTEND_URL=http://localhost:5173
APP_URL=http://localhost:8000
ENVIRONMENT=development
SECRET_KEY=your-secret-key-here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-admin-password
```

## Step 3: Migrate Data from SQLite (if applicable)

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
📦 Target: PostgreSQL (Supabase)

1️⃣  Creating database schema in PostgreSQL...
   ✅ Schema created

2️⃣  Migrating users...
   ✅ Migrated 2 users

3️⃣  Migrating chat sessions...
   ✅ Migrated 15 sessions

... (continues for each table)

✅ Migration complete!
```

## Step 4: Restart Backend

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
[STARTUP] Initializing database at postgresql+asyncpg://postgres.<ref>@aws-0-<region>.pooler.supabase.com:6543/postgres...
[STARTUP] Database initialization complete.
[STARTUP] PRGuard backend started successfully.
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
  "database_connected": true,
  "llm_key_configured": true,
  "env_loaded": true
}
```

## Step 5: Verify Everything Works

### 5.1 Admin Dashboard
- Visit: http://localhost:5173/admin/login
- Login with your configured admin credentials
- Dashboard should load and show users

### 5.2 User Dashboard
- Test regular user login via GitHub OAuth
- Create a new chat session
- Verify messages are saved to PostgreSQL

### 5.3 Database Size
Check on Supabase dashboard how much data is stored:
- https://supabase.com/dashboard → Your Project → Database → Database Size

## Troubleshooting

### `(ENOTFOUND) tenant/user postgres.<ref> not found`
This error means the Supabase project is **paused** or **deleted**, NOT a DNS failure.
- **Paused project**: Free-tier projects auto-pause after 7 days of inactivity. Go to the Supabase dashboard and click **"Restore project"**. Wait ~2 minutes, then retry.
- **Deleted project**: Create a new project and update the connection string.
- **Wrong region in URL**: Verify the hostname region matches your project's region in **Project Settings → General**.

### Connection Error: "could not connect to server"
- Verify connection string is correct
- Check Supabase dashboard for active database
- Ensure `sslmode=require` is in the connection string

### Slow Queries After Migration
- Supabase includes built-in query performance monitoring
- Check the **SQL Editor** in Supabase dashboard to run `EXPLAIN ANALYZE` on slow queries
- Add indexes as needed for your queries

### Prepared Statement Errors
If you see errors about prepared statements or `statement_cache_size`:
- The backend automatically disables prepared statement caching when it detects a Supabase pooler URL
- Ensure your `DATABASE_URL` contains `pooler.supabase.com` (not the direct connection host)

## Production Deployment

When deploying to production (Render, Railway, etc.):

1. **Environment Variables** in your hosting platform:
   ```
   DATABASE_URL=postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
   ENVIRONMENT=production
   DEBUG=false
   ```

2. **Backend URL** (for frontend CORS):
   ```
   APP_URL=https://your-api-domain.com
   FRONTEND_URL=https://your-frontend-domain.com
   ```

3. **SSL/TLS**:
   - Supabase handles SSL (`sslmode=require` already included)
   - Frontend should use HTTPS

4. **Connection Pooling**:
   - Use the **transaction pooler** (port 6543) for serverless deployments
   - The backend automatically configures small local pool sizes when it detects the Supabase pooler
   - Do NOT use the session pooler (port 5432) with serverless/ephemeral backends

5. **Paused Projects**:
   - Free-tier Supabase projects auto-pause after 7 days of inactivity
   - For production, upgrade to a paid Supabase plan to prevent auto-pausing
   - Alternatively, set up a health-check pinger to keep the project active

## Cleanup

### Keep SQLite Backup (if migrating)
After verifying everything works:
```bash
# Create backup
cp prguard.db prguard-backup.db

# Later, if everything works, can delete:
# rm prguard.db
```

## Support

- Supabase Docs: https://supabase.com/docs
- Supabase Connection Pooling: https://supabase.com/docs/guides/database/connecting-to-postgres#connection-pooler
- PRGuard Issues: Check backend logs for database-related errors
- PostgreSQL Issues: Consult PostgreSQL documentation

---

That's it! Your PRGuard backend is now using Supabase PostgreSQL. 🎉
