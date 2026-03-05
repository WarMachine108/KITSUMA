import psycopg2
import sys

def signup(sign_up, new_pass): 
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="kitsumadb",
            user="postgres",
            password="Usaid@10",
            port="5432"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE login = %s;", (sign_up,))
        ifIDexists = cursor.fetchall()
        if (ifIDexists):
            conn.close()
            return 1
        cursor.execute("INSERT INTO users (login, password) VALUES (%s, %s);", (sign_up, new_pass))
        conn.commit()
        conn.close()
        return 0 
    except Exception as e:
        return 2
def login(login_id, password): 
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="kitsumadb",
            user="postgres",
            password="Usaid@10",
            port="5432"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE login = %s AND password = crypt(%s, password);", (login_id, password))
        output = cursor.fetchall()
        if (output): 
            conn.close()
            return 0
        else:
            conn.close()
            return 1
    except Exception as e:
        return 2
def getdata(login_id): 
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="kitsumadb",
            user="postgres",
            password="Usaid@10",
            port="5432"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT structure from personalized_files where user_login = %s; ", (login_id, ))
        output = cursor.fetchall()
        if (output): 
            with open('structure.txt', 'w+') as f: 
                f.write(output[0][0])
            conn.close()
            return 0
        else:
            conn.close()
            return 1
    except Exception as e:
        return 2
def putfilecontent(filename, file):
    try:
        with open(file, "r") as f:
            filecontent = f.read()
        conn = psycopg2.connect(
            host="localhost",
            database="kitsumadb",
            user="postgres",
            password="Tanmay10",
            port="5432"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT filename from file where filename = %s;", (filename, ))
        output = cursor.fetchall()
        if (output): 
            cursor.execute("UPDATE file set file_content = %s where filename = %s;", (filecontent, filename))
        else: 
            cursor.execute("Insert into file (filename, file_content) values (%s, %s);", (filename, filecontent))
        conn.commit()
        conn.close() 
    except Exception as e: 
        return 2    
def getfiledata(file_path,base_path,file_name): 
    try:
        conn = psycopg2.connect(
            host="localhost",
            database="kitsumadb",
            user="postgres",
            password="Usaid@10",
            port="5432"
        )
        cursor = conn.cursor()
        print(file_name)
        cursor.execute("SELECT file_content from file where filename = %s; ", (file_name, ))
        output = cursor.fetchall()
        location=base_path+'/'+file_path
        if (output): 
            with open(location, 'w+') as f: 
                f.write(output[0][0])
            conn.close()
            return 0
        else:
            conn.close()
            return 1
    except Exception as e:
        return 2

if __name__ == "__main__":
    operation = sys.argv[1]
    if operation == "S" or operation == "L":
        user = sys.argv[2]
        pwd = sys.argv[3]

        if operation == "S":
            code = signup(user, pwd)
        else:
            code = login(user, pwd)

    elif operation == "G":
        user = sys.argv[2]
        code = getdata(user)

    elif operation == "A": 
        filename = sys.argv[2]
        
        file = sys.argv[3]
        code = putfilecontent(filename, file)
        
    elif operation == "GF":
        file_path=sys.argv[2]
        base_path=sys.argv[3]
        file_name=sys.argv[4]
        code = getfiledata(file_path,base_path,file_name)

    else:
        code = 2

    sys.exit(code)