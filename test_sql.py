import sqlite3
 
# 连接到 SQLite 数据库
# 如果文件不存在，会自动在当前目录创建:
conn = sqlite3.connect('db.sqlite3')
 
# 创建一个 Cursor 对象并使用其执行 SQL 命令:
cursor = conn.cursor()
 
# 使用 cursor 执行添加列的操作:
cursor.execute('ALTER TABLE tasks ADD COLUMN dify_conversation_id VARCHAR(255) DEFAULT "";')
 
# 提交事务:
conn.commit()
 
# 关闭连接:
conn.close()