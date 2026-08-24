import sqlite3

# Dummy user patterns to delete
dummy_users = [
    'user-a', 'user-b', 'e2e-user', 'usera', 'userb',
    'simuser1', 'simuser2', 'autha', 'authb'
]

con = sqlite3.connect('prguard.db')
cur = con.cursor()

for user in dummy_users:
    cur.execute('SELECT id FROM users WHERE username = ?', (user,))
    result = cur.fetchone()
    if result:
        user_id = result[0]
        # Delete associated records
        cur.execute('DELETE FROM user_api_keys WHERE user_id = ?', (user_id,))
        cur.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
        cur.execute('DELETE FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE user_id = ?)', (user_id,))
        cur.execute('DELETE FROM reviews WHERE user_id = ?', (user_id,))
        cur.execute('DELETE FROM connected_repositories WHERE user_id = ?', (user_id,))
        cur.execute('DELETE FROM users WHERE id = ?', (user_id,))
        print(f'Deleted: {user}')

con.commit()
con.close()
print('Cleanup complete.')
