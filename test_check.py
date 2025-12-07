"""
测试脚本 - 用于测试各个模块的功能
"""
import yaml
import logging
from datetime import datetime

from logger_config import setup_logger
from database import Database
from bilibili_checker import BilibiliChecker
from email_sender import EmailSender


def test_bilibili_checker():
    """测试B站检测模块"""
    print("\n" + "="*60)
    print("测试B站检测模块")
    print("="*60)
    
    checker = BilibiliChecker()

    # 支持命令行非交互模式（便于 CI / 自动化），使用环境变量或传入参数
    import argparse

    parser = argparse.ArgumentParser(description='测试 B 站检测模块')
    parser.add_argument('--uid', '-u', default=None, help='要测试的 B 站 UID（默认使用 1）')
    parser.add_argument('--no-input', action='store_true', help='非交互模式，遇到需要输入时不阻塞')
    args, _ = parser.parse_known_args()

    import sys

    if args.uid:
        test_uid = args.uid
    elif args.no_input or not sys.stdin.isatty():
        test_uid = "1"
    else:
        test_uid = input("请输入要测试的B站UID（直接回车使用示例UID 1）: ").strip()
        if not test_uid:
            test_uid = "1"

    print(f"\n正在检测UID: {test_uid}")
    is_active, last_active_time, status_info = checker.check_user_activity(test_uid)
    
    print(f"\n检测结果:")
    print(f"  是否活跃: {is_active}")
    print(f"  最后活动时间: {last_active_time}")
    print(f"  状态信息: {status_info}")
    
    if last_active_time:
        days_inactive = checker.calculate_inactive_days(last_active_time)
        print(f"  不活跃天数: {days_inactive}")


def test_database():
    """测试数据库模块"""
    print("\n" + "="*60)
    print("测试数据库模块")
    print("="*60)
    
    db = Database("test.db")
    
    # 测试保存检查记录
    print("\n保存测试记录...")
    db.save_check_record(
        qq_number="123456789",
        bilibili_uid="12345678",
        check_time=datetime.now(),
        last_active_time=datetime.now(),
        is_active=True,
        days_inactive=0,
        status_info="测试记录"
    )
    print("✓ 记录保存成功")
    
    # 测试查询
    print("\n查询最新记录...")
    record = db.get_latest_check_record("123456789", "12345678")
    if record:
        print(f"✓ 查询成功: {record}")
    else:
        print("✗ 查询失败")
    
    # 清理测试数据库
    import os
    if os.path.exists("test.db"):
        os.remove("test.db")
        print("\n✓ 测试数据库已清理")


def test_email_sender():
    """测试邮件发送模块"""
    print("\n" + "="*60)
    print("测试邮件发送模块")
    print("="*60)
    
    try:
        with open("config.yaml", 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        email_config = config['email']
        
        sender = EmailSender(
            smtp_server=email_config['smtp_server'],
            smtp_port=email_config['smtp_port'],
            sender_email=email_config['sender_email'],
            sender_password=email_config['sender_password'],
            receiver_email=email_config['receiver_email'],
            subject_prefix=email_config['subject_prefix']
        )
        
        print("\n发送测试邮件...")
        success = sender.send_email(
            subject="测试邮件",
            body="这是一封测试邮件，用于验证邮件发送功能是否正常。",
            html_body="<html><body><h1>测试邮件</h1><p>这是一封测试邮件，用于验证邮件发送功能是否正常。</p></body></html>"
        )
        
        if success:
            print("✓ 测试邮件发送成功！请检查收件箱。")
        else:
            print("✗ 测试邮件发送失败，请检查配置和日志。")
            
    except FileNotFoundError:
        print("✗ 配置文件不存在，请先配置 config.yaml")
    except Exception as e:
        print(f"✗ 测试失败: {e}")


def main():
    """主测试函数"""
    # 设置日志
    setup_logger(log_level="INFO", log_file="test.log")
    
    print("B站账号生命状态监控系统 - 测试工具")
    print("="*60)
    
    while True:
        print("\n请选择测试项目:")
        print("1. 测试B站检测模块")
        print("2. 测试数据库模块")
        print("3. 测试邮件发送模块")
        print("4. 运行所有测试")
        print("0. 退出")
        
        choice = input("\n请输入选项 (0-4): ").strip()
        
        if choice == "0":
            print("\n退出测试")
            break
        elif choice == "1":
            test_bilibili_checker()
        elif choice == "2":
            test_database()
        elif choice == "3":
            test_email_sender()
        elif choice == "4":
            test_bilibili_checker()
            test_database()
            test_email_sender()
        else:
            print("无效选项，请重新选择")


if __name__ == "__main__":
    main()

