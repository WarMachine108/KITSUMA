import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        database="kitsumadb",
        user="postgres",
        password="Tanmay10",
        port="5432"
    )

    login_id=input("Enter your LoginID: ")
    password=input("Enter your Password: ")

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE login = %s AND password = crypt(%s, password);",(login_id,password))
    output = cursor.fetchall()
    if output :
        exists=True
    else:
        exists=False
    if exists:
        cursor.execute("select file_content from personalized_files where user_login=%s",(login_id,))
        output=cursor.fetchall()
        first = True
        with open('structure.txt','w+') as f:
            if (first):
                f.write(login_id)
                first = False 
            f.write(output[0][0])
        cursor.execute("SELECT file_content from file where fileno = 2")
        output2 = cursor.fetchall()
        if output2: 
            with open("filecontent.txt", "w+") as f: 
                f.write(output2[0][0])
        with open ('define.cpp', 'r') as f:
            filecontent = f.read()
        cursor.execute("insert into file(filename, file_content) values (%s, %s);", ("define.cpp", filecontent))
        cursor.execute("insert into pushes (fileno, file_content, message, user_login) values (%s, %s, %s, %s);", (1, filecontent, "TEST MESSAGE FOR NOW WILL DELETE LATER 2", login_id))
    conn.commit() 
    cursor.close()
    conn.close()

except Exception as e:
    print("Error:", e)