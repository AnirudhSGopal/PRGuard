# Supabase PostgreSQL Migration Checklist

## Quick Start (5 Steps)

### Step 1: Create Supabase Database ⏱️ 5 mins
- [ ] Go to https://supabase.com/dashboard
- [ ] Sign up with GitHub / Email
- [ ] Click "New project" → name: `prguard`, pick a region close to your deployment
- [ ] Copy connection string from **Project Settings → Database → Connection string → Transaction pooler**
  - Save it somewhere safe (you'll need this)

### Step 2: Update Environment File ⏱️ 2 mins
- [ ] Open your `.env` (project root or `backend/.env`)
- [ ] Replace this line (if migrating from SQLite):
  ```
  DATABASE_URL=sqlite+aiosqlite:///./prguard.db
  ```
  With your Supabase connection string:
  ```
  DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
  ```
- [ ] Save file

### Step 3: Run Migration Script (if migrating from SQLite) ⏱️ 5 mins
In terminal (from `backend/` folder):
```bash
# Activate environment if needed
.\.venv\Scripts\Activate.ps1

# Run migration
python migrate_sqlite_to_postgres.py
```
Expected: "✅ Migration complete!"

### Step 4: Restart Backend ⏱️ 2 mins
```bash
# Stop old backend (CTRL+C if running)
# Then restart:
python run.py
```
Expected: "[STARTUP] PRGuard backend started successfully."

### Step 5: Verify Everything ⏱️ 3 mins
- [ ] Visit http://localhost:8000/health → returns 200 with `database_connected: true` ✓
- [ ] Admin login works: http://localhost:5173/admin/login
- [ ] Dashboard shows users from PostgreSQL ✓

---

## File Locations

| File | Purpose |
|------|---------|
| `.env` (project root) | **Edit here** — Your database connection |
| `backend/.env.example` | Reference example |
| `backend/migrate_sqlite_to_postgres.py` | **Run this** — Migration script (SQLite → PostgreSQL) |
| `SUPABASE_SETUP_GUIDE.md` | Detailed guide |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `(ENOTFOUND) tenant/user ... not found` | Project is paused — restore it in the Supabase dashboard |
| "could not connect to server" | Check connection string in `.env` |
| Migration fails halfway | Delete created tables in Supabase SQL Editor, run script again |
| Backend won't start | Check `DATABASE_URL` format — must use port `6543` for transaction pooler |
| Admin dashboard shows no users | Migration didn't complete — run script again |
| Prepared statement errors | Ensure URL contains `pooler.supabase.com` (not direct connection) |

---

## Need Help?

1. **Supabase Connection String Format:**
   ```
   postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
   ```

2. **Check What's in Supabase:**
   - Go to https://supabase.com/dashboard
   - Select your project
   - Use the SQL Editor to run queries

3. **Still Stuck?**
   - Check backend log for error messages
   - Verify `.env` file exists and has correct URL
   - Ensure migration script completed successfully
   - Check if the Supabase project is paused (free tier auto-pauses after 7 days)

---

## After Migration (Optional Cleanup)

```bash
# Keep SQLite backup (recommended)
cp prguard.db prguard-sqlite-backup.db

# Later, if everything works, can delete:
# rm prguard.db
```

---

**Total Time:** ~20 minutes ⏱️

Questions? Check `SUPABASE_SETUP_GUIDE.md` for detailed instructions.
