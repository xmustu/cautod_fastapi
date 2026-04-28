"""
SystemConfig 模型测试脚本

测试功能：
1. 创建 SystemConfig 记录
2. 读取 SystemConfig 记录
3. 更新 SystemConfig 记录
4. 验证单例模式（只保留一条记录）
5. 测试默认值
"""

import asyncio
from tortoise import run_async, Tortoise
from database.models import SystemConfig
from database.settings import TORTOISE_ORM_MYSQL, TORTOISE_ORM_SQLITE
from config import settings
from datetime import datetime


async def test_system_config():
    """测试 SystemConfig 模型的各种操作"""
    
    # 初始化数据库连接
    if settings.SQLMODE == "MYSQL":
        config = TORTOISE_ORM_MYSQL
    else:
        config = TORTOISE_ORM_SQLITE
    
    await Tortoise.init(config=config)
    await Tortoise.generate_schemas()
    
    print("=" * 60)
    print("SystemConfig 模型测试")
    print("=" * 60)
    
    try:
        # 测试 1: 检查现有配置
        print("\n[测试 1] 检查现有配置...")
        existing_config = await SystemConfig.first()
        if existing_config:
            print(f"✓ 找到现有配置 (ID: {existing_config.config_id})")
            print(f"  - max_tasks_per_user: {existing_config.max_tasks_per_user}")
            print(f"  - max_conversations_per_user: {existing_config.max_conversations_per_user}")
            print(f"  - enable_registration: {existing_config.enable_registration}")
            print(f"  - enable_email_verification: {existing_config.enable_email_verification}")
            print(f"  - maintenance_mode: {existing_config.maintenance_mode}")
            print(f"  - created_at: {existing_config.created_at}")
            print(f"  - updated_at: {existing_config.updated_at}")
        else:
            print("✗ 未找到现有配置")
        
        # 测试 2: 创建新配置（如果不存在）
        print("\n[测试 2] 创建/更新配置...")
        if not existing_config:
            new_config = await SystemConfig.create(
                max_tasks_per_user=100,
                max_conversations_per_user=50,
                enable_registration=True,
                enable_email_verification=True,
                maintenance_mode=False
            )
            print(f"✓ 创建新配置成功 (ID: {new_config.config_id})")
            config_to_test = new_config
        else:
            config_to_test = existing_config
            print(f"✓ 使用现有配置 (ID: {config_to_test.config_id})")
        
        # 测试 3: 读取配置
        print("\n[测试 3] 读取配置...")
        config = await SystemConfig.first()
        if config:
            print("✓ 配置读取成功:")
            print(f"  - config_id: {config.config_id}")
            print(f"  - max_tasks_per_user: {config.max_tasks_per_user}")
            print(f"  - max_conversations_per_user: {config.max_conversations_per_user}")
            print(f"  - enable_registration: {config.enable_registration}")
            print(f"  - enable_email_verification: {config.enable_email_verification}")
            print(f"  - maintenance_mode: {config.maintenance_mode}")
        else:
            print("✗ 配置读取失败")
            return
        
        # 测试 4: 更新配置
        print("\n[测试 4] 更新配置...")
        old_max_tasks = config.max_tasks_per_user
        new_max_tasks = 200
        config.max_tasks_per_user = new_max_tasks
        config.enable_registration = False
        config.maintenance_mode = True
        await config.save()
        
        # 验证更新
        updated_config = await SystemConfig.first()
        if updated_config and updated_config.max_tasks_per_user == new_max_tasks:
            print(f"✓ 配置更新成功")
            print(f"  - max_tasks_per_user: {old_max_tasks} -> {updated_config.max_tasks_per_user}")
            print(f"  - enable_registration: {updated_config.enable_registration}")
            print(f"  - maintenance_mode: {updated_config.maintenance_mode}")
            print(f"  - updated_at: {updated_config.updated_at}")
        else:
            print("✗ 配置更新失败")
        
        # 测试 5: 验证单例模式（只保留一条记录）
        print("\n[测试 5] 验证单例模式...")
        all_configs = await SystemConfig.all()
        config_count = len(all_configs)
        print(f"  当前配置记录数: {config_count}")
        if config_count == 1:
            print("✓ 单例模式验证通过（只有一条记录）")
        else:
            print(f"⚠ 警告：发现 {config_count} 条记录，应该只有 1 条")
            print("  建议：删除多余的记录以保持单例模式")
        
        # 测试 6: 测试默认值
        print("\n[测试 6] 测试默认值...")
        # 创建一个临时配置对象（不保存）来测试默认值
        temp_config = SystemConfig()
        print("  默认值测试:")
        print(f"  - max_tasks_per_user 默认值: {temp_config.max_tasks_per_user}")
        print(f"  - max_conversations_per_user 默认值: {temp_config.max_conversations_per_user}")
        print(f"  - enable_registration 默认值: {temp_config.enable_registration}")
        print(f"  - enable_email_verification 默认值: {temp_config.enable_email_verification}")
        print(f"  - maintenance_mode 默认值: {temp_config.maintenance_mode}")
        
        # 测试 7: 恢复测试数据（可选）
        print("\n[测试 7] 恢复测试数据...")
        config.max_tasks_per_user = 100
        config.enable_registration = True
        config.maintenance_mode = False
        await config.save()
        print("✓ 已恢复为原始测试值")
        
        # 测试 8: 查询所有配置（应该只有一条）
        print("\n[测试 8] 查询所有配置...")
        all_configs = await SystemConfig.all()
        print(f"  找到 {len(all_configs)} 条配置记录")
        for idx, cfg in enumerate(all_configs, 1):
            print(f"  配置 {idx}:")
            print(f"    - ID: {cfg.config_id}")
            print(f"    - max_tasks_per_user: {cfg.max_tasks_per_user}")
            print(f"    - created_at: {cfg.created_at}")
        
        print("\n" + "=" * 60)
        print("所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 关闭数据库连接
        await Tortoise.close_connections()
        print("\n✓ 数据库连接已关闭")


if __name__ == "__main__":
    print("开始测试 SystemConfig 模型...")
    print(f"数据库模式: {settings.SQLMODE}")
    print(f"数据库: {settings.MYSQL_DATABASE if settings.SQLMODE == 'MYSQL' else 'SQLite'}")
    print()
    
    run_async(test_system_config())

