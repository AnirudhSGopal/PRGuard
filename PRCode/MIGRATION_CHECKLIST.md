# Neon PostgreSQL Migration Checklist

## Quick Start (5 Steps)

### Step 1: Create Neon Database ⏱️ 5 mins
- [ ] Go to https://console.neon.tech
- [ ] Sign up with GitHub / Email
- [ ] Click "Create project" → name: `prguard`
- [ ] Copy connection string from dashboard
  - Save it somewhere safe (you'll need this)

### Step 2: Update Environment File ⏱️ 2 mins
- [ ] Open `backend/.env`
- [ ] Replace this line:
  ```
  DATABASE_URL=sqlite+aiosqlite:///./prguard.db
  ```
  With your Neon connection string:
  ```
  DATABASE_URL=postgresql+asyncpg://user:password@host.neon.tech/dbname?sslmode=require
  ```
- [ ] Save file

### Step 3: Run Migration Script ⏱️ 5 mins
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
- [ ] Visit http://localhost:8000/health → returns 200 ✓
- [ ] Admin login works: http://localhost:5175/admin/login
- [ ] Dashboard shows users from PostgreSQL ✓

---

## File Locations

| File | Purpose |
|------|---------|
| `backend/.env` | **Edit here** - Your database connection |
| `backend/.env.example` | Reference example |
| `backend/migrate_sqlite_to_postgres.py` | **Run this** - Migration script |
| `NEON_SETUP_GUIDE.md` | Detailed guide |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "could not connect to server" | Check connection string in `.env` |
| Migration fails halfway | Delete tables in Neon, run script again |
| Backend won't start | Check `DATABASE_URL` format |
| Admin dashboard shows no users | Migration didn't complete - run script again |

---

## Need Help?

1. **Neon Connection String Format:**
   ```
   postgresql+asyncpg://user:password@host.neon.tech/dbname?sslmode=require
   ```

2. **Check What's in Neon:**
   - Go to https://console.neon.tech
   - Select your project
   - Look at SQL Editor to run queries

3. **Still Stuck?**
   - Check backend log for error messages
   - Verify `.env` file exists and has correct URL
   - Ensure migration script completed successfully

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

Questions? Check `NEON_SETUP_GUIDE.md` for detailed instructions.
