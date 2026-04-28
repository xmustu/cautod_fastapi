# 环境隔离最佳实践指南

## ⚠️ 重要提示

**生产环境和开发环境共享同一个 MySQL 容器不是推荐做法**，但在资源受限的情况下，如果必须这样做，请遵循以下安全措施。

## 当前配置检查清单

### ✅ 必须做到

1. **不同的数据库名称**
   ```env
   # .env.dev
   MYSQL_DATABASE=cautod_dev
   
   # .env.prod
   MYSQL_DATABASE=cautod_prod
   ```

2. **不同的数据库用户**（强烈推荐）
   ```sql
   -- 开发环境用户
   CREATE USER 'cautod_dev'@'%' IDENTIFIED BY 'dev_password';
   GRANT ALL PRIVILEGES ON cautod_dev.* TO 'cautod_dev'@'%';
   
   -- 生产环境用户
   CREATE USER 'cautod_prod'@'%' IDENTIFIED BY 'strong_prod_password';
   GRANT ALL PRIVILEGES ON cautod_prod.* TO 'cautod_prod'@'%';
   ```

3. **环境变量明确区分**
   ```env
   # .env.dev
   ENVIRONMENT=dev
   DEBUG_MODE=true
   
   # .env.prod
   ENVIRONMENT=prod
   DEBUG_MODE=false
   ```

4. **资源监控和限制**
   - 监控 MySQL 容器的 CPU 和内存使用
   - 设置合理的连接数限制
   - 为每个数据库设置独立的连接池大小

### ⚠️ 风险缓解措施

1. **定期备份**
   ```bash
   # 生产环境数据库备份
   mysqldump -u cautod_prod -p cautod_prod > backup_prod_$(date +%Y%m%d).sql
   
   # 开发环境数据库备份
   mysqldump -u cautod_dev -p cautod_dev > backup_dev_$(date +%Y%m%d).sql
   ```

2. **访问控制**
   - 限制开发环境对生产数据库的访问
   - 使用防火墙规则限制连接来源
   - 启用 MySQL 的审计日志

3. **监控和告警**
   - 监控数据库连接数
   - 监控慢查询
   - 设置资源使用告警

## 推荐的迁移路径

### 短期（当前方案改进）

1. ✅ 使用不同的数据库名称（已完成）
2. ⚠️ 使用不同的数据库用户（待实现）
3. ⚠️ 添加资源监控（待实现）

### 中期（部分隔离）

1. 使用 Docker Compose 的独立网络
2. 为每个环境设置独立的连接池
3. 实现独立的备份策略

### 长期（完全隔离）

1. **独立的 MySQL 容器**
   - 开发环境：`mysql-dev` 容器
   - 生产环境：`mysql-prod` 容器
   - 完全隔离，互不影响

2. **独立的服务器/实例**（生产环境）
   - 使用云数据库服务（RDS、云数据库等）
   - 自动备份和恢复
   - 高可用配置

## 配置示例

### 开发环境配置 (.env.dev)

```env
ENVIRONMENT=dev
DEBUG_MODE=true

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=cautod_dev
MYSQL_PASSWORD=dev_password
MYSQL_DATABASE=cautod_dev
SQLMODE=MYSQL
```

### 生产环境配置 (.env.prod)

```env
ENVIRONMENT=prod
DEBUG_MODE=false

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=cautod_prod
MYSQL_PASSWORD=strong_prod_password_here
MYSQL_DATABASE=cautod_prod
SQLMODE=MYSQL
```

## 安全检查脚本

定期运行以下检查：

```bash
# 检查数据库用户权限
mysql -u root -p -e "SELECT User, Host, Db FROM mysql.db WHERE Db LIKE 'cautod%';"

# 检查数据库大小
mysql -u root -p -e "SELECT table_schema AS 'Database', 
  ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)' 
  FROM information_schema.tables 
  WHERE table_schema LIKE 'cautod%' 
  GROUP BY table_schema;"

# 检查连接数
mysql -u root -p -e "SHOW PROCESSLIST;"
```

## 总结

虽然共享容器在技术上可行，但**强烈建议尽快迁移到独立的容器或实例**。如果当前必须共享，请：

1. ✅ 使用不同的数据库名称
2. ⚠️ 使用不同的数据库用户
3. ⚠️ 实施严格的访问控制
4. ⚠️ 建立监控和告警机制
5. ⚠️ 制定备份和恢复计划

**记住：生产数据的安全和稳定性是第一优先级！**

