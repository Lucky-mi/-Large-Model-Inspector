import psycopg2

conn=psycopg2.connect(database="finance01",user="python01_user51",password="python01_user51@123",host="110.41.115.206",port=8000)  # 使用connect()建立与数据库的连接，并获取数据库连接对象

cursor=conn.cursor() #使用连接对象的cursor()获取游标对象

conn.commit()
result = cursor.fetchall()
print (result)
conn.close()  # 使用close()关闭数据库连接和游标对象