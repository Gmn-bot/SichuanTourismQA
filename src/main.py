#!/usr/bin/env python3
# coding: utf-8

"""
主程序入口，提供命令行接口执行不同的功能。
"""

import os
import sys
import argparse
from typing import List

# 将项目根目录添加到系统路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入必要的模块
from src.utils.logger import get_logger
from src.utils.config import get_config, check_required_configs

# 创建日志记录器
logger = get_logger(__name__)

def setup_parser() -> argparse.ArgumentParser:
    """
    设置命令行参数解析器
    
    Returns:
        命令行参数解析器
    """
    parser = argparse.ArgumentParser(description="四川旅游知识图谱问答系统")
    
    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # web 命令 - 启动Web服务
    web_parser = subparsers.add_parser("web", help="启动Web服务")
    web_parser.add_argument("--host", type=str, help="主机地址")
    web_parser.add_argument("--port", type=int, help="端口号")
    web_parser.add_argument("--debug", action="store_true", help="启用调试模式")
    
    # chat 命令 - 启动命令行聊天
    chat_parser = subparsers.add_parser("chat", help="启动命令行聊天")
    
    # import 命令 - 导入知识图谱数据
    import_parser = subparsers.add_parser("import", help="导入知识图谱数据")
    import_parser.add_argument("--file", type=str, help="三元组数据文件路径")
    import_parser.add_argument("--clear", action="store_true", help="导入前清空数据库")
    
    # crawl 命令 - 爬取旅游数据
    crawl_parser = subparsers.add_parser("crawl", help="爬取旅游数据")
    crawl_parser.add_argument("--output", type=str, help="输出文件路径")
    crawl_parser.add_argument("--limit", type=int, help="爬取的最大条目数")
    
    # test 命令 - 运行测试
    test_parser = subparsers.add_parser("test", help="运行测试")
    test_parser.add_argument("--module", type=str, help="指定要测试的模块")
    
    return parser

def start_web_server(host: str = None, port: int = None, debug: bool = None) -> None:
    """
    启动Web服务
    
    Args:
        host: 主机地址，默认从配置获取
        port: 端口号，默认从配置获取
        debug: 调试模式，默认从配置获取
    """
    # 确保配置完整
    required_configs = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]
    if not check_required_configs(required_configs):
        logger.error("缺少必要的数据库配置，无法启动Web服务")
        return
    
    # 使用参数值或从配置获取
    host = host or get_config("FLASK_HOST", "0.0.0.0")
    port = port or int(get_config("FLASK_PORT", "5000"))
    debug = debug if debug is not None else get_config("FLASK_DEBUG", "False").lower() == "true"
    
    # 导入并启动Web服务
    try:
        from Backend_code import app
        
        # 显示服务信息
        logger.info(f"启动Web服务 - 地址: {host}:{port}, 调试模式: {'启用' if debug else '禁用'}")
        
        # 启动Flask应用
        app.run(host=host, port=port, debug=debug)
    
    except ImportError as e:
        logger.error(f"导入Web服务模块失败: {e}")
    except Exception as e:
        logger.error(f"启动Web服务失败: {e}")

def start_chat() -> None:
    """启动命令行聊天界面"""
    # 确保配置完整
    required_configs = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]
    if not check_required_configs(required_configs):
        logger.error("缺少必要的数据库配置，无法启动聊天功能")
        return
    
    try:
        from tourist_qa_main import TouristQABot
        
        logger.info("启动命令行聊天界面")
        bot = TouristQABot()
        bot.chat()
        
    except ImportError as e:
        logger.error(f"导入聊天模块失败: {e}")
    except Exception as e:
        logger.error(f"启动聊天功能失败: {e}")

def import_data(file_path: str = None, clear: bool = False) -> None:
    """
    导入知识图谱数据
    
    Args:
        file_path: 三元组数据文件路径
        clear: 导入前是否清空数据库
    """
    # 确保配置完整
    required_configs = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"]
    if not check_required_configs(required_configs):
        logger.error("缺少必要的数据库配置，无法导入数据")
        return
    
    # 使用参数值或默认值
    file_path = file_path or os.path.join(project_root, "景点知识图谱_三元组.csv")
    
    try:
        logger.info(f"开始导入知识图谱数据 - 文件: {file_path}, 清空数据库: {'是' if clear else '否'}")
        
        # 导入数据导入模块
        import py2neo_data_import
        
        # 设置参数并执行导入
        py2neo_data_import.main(file_path, clear)
        
        logger.info("数据导入完成")
        
    except ImportError as e:
        logger.error(f"导入数据处理模块失败: {e}")
    except Exception as e:
        logger.error(f"导入数据失败: {e}")

def run_crawler(output_path: str = None, limit: int = None) -> None:
    """
    运行爬虫爬取旅游数据
    
    Args:
        output_path: 输出文件路径
        limit: 爬取的最大条目数
    """
    try:
        output_path = output_path or os.path.join(project_root, "爬取数据.csv")
        limit = limit or 100
        
        logger.info(f"开始爬取旅游数据 - 输出: {output_path}, 限制: {limit}条")
        
        # 导入爬虫模块
        import ctrip_crawler

        # 设置参数并执行爬取
        ctrip_crawler.main(output_path, limit)
        
        logger.info("数据爬取完成")
        
    except ImportError as e:
        logger.error(f"导入爬虫模块失败: {e}")
    except Exception as e:
        logger.error(f"爬取数据失败: {e}")

def run_tests(module: str = None) -> None:
    """
    运行测试
    
    Args:
        module: 指定要测试的模块，如果为None则运行所有测试
    """
    import unittest
    
    logger.info(f"开始运行测试 {module or '(所有)'}")
    
    tests_dir = os.path.join(project_root, "tests")
    
    if module:
        # 运行特定模块的测试
        test_file = os.path.join(tests_dir, f"test_{module}.py")
        if os.path.exists(test_file):
            unittest.main(module=f"tests.test_{module}")
        else:
            logger.error(f"测试模块不存在: {test_file}")
    else:
        # 运行所有测试
        loader = unittest.TestLoader()
        tests = loader.discover(tests_dir)
        runner = unittest.TextTestRunner()
        runner.run(tests)
    
    logger.info("测试运行完成")

def main(args: List[str] = None) -> None:
    """
    主函数，解析命令行参数并执行相应功能
    
    Args:
        args: 命令行参数，如果为None则使用sys.argv
    """
    parser = setup_parser()
    args = parser.parse_args(args)
    
    # 根据命令执行相应的功能
    if args.command == "web":
        start_web_server(args.host, args.port, args.debug)
    elif args.command == "chat":
        start_chat()
    elif args.command == "import":
        import_data(args.file, args.clear)
    elif args.command == "crawl":
        run_crawler(args.output, args.limit)
    elif args.command == "test":
        run_tests(args.module)
    else:
        # 如果没有提供命令，显示帮助信息
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
        sys.exit(1)
