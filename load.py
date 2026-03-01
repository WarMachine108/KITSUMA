import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="kitsumadb",
        user="postgres",
        password="Tanmay10"
    )

    print("Connected successfully!")

    cur = conn.cursor()

    cur.execute("SELECT login FROM users;")

    rows = cur.fetchall()

    for row in rows:
        print("User:", row[0])

    cur.close()
    conn.close()

except Exception as e:
    print("Error:", e)