1.git clone https://github.com/xmustu/cautod.git

2.conda create --name fastapi python=3.9

3.conda activate fastapi

4.pip install -r requirements.txt

5.cd cautod

6.python main.py



在 浏览器或其他工具访问 http://127.0.0.1:8080/docs 查看FastAPI 交互式 API 文档

关于数据库已配置，重新配置，删除pyproject.toml、migrations 和 db.sqlite3, 参照 database/aerich.py 步骤使用 aerich迁移工具
