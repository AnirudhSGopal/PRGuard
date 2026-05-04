import sqlite3
con = sqlite3.connect('prguard.db')
cur = con.cursor()
cur.execute('SELECT id, username, role FROM users ORDER BY created_at')
for r in cur.fetchall():
    print(f'{r[1]:20} | {r[2]:8}')
con.close()
