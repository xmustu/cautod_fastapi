"""
aerich 数据迁移工具
1. 初始化配置，只需要使用一次
aerich init -t settings.TORTOISE_ORM # TORTOISE_ORM配置的位置)

2.初始化数据库，一般情况下只用一次
aerich init-db

3.更新模型并进行迁移
aerich migrate [--name] (标记修改操作) #  aerich migrate --name add_column

4. 重新执行迁移，写入数据库
aerich upgrade
"""