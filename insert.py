import psycopg2
import sys


conn = psycopg2.connect(
    host="localhost",
    database="kitsumadb",
    user="postgres",
    password="Usaid@10",
    port="5432"
)
cursor = conn.cursor()
with open('C:/Users/usaid/OneDrive/Desktop/SOURCE/usaid_codes/programs/aiml_prac.py', 'r') as f: 
    output=f.read()
cursor.execute("INSERT INTO file (filename, file_content) VALUES (%s, %s);", ('nums.py', output))
conn.commit()
conn.close()