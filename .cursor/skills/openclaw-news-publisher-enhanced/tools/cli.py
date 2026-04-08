#!/usr/bin/env python3
"""
命令行接口工具
提供用户友好的命令来控制白名单功能
"""

import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

# 添加core目录到路径
sys.path.insert(0, str(Path(__file__).parent / "core"))

from whitelist_manager import WhitelistManager
from first_run_discovery import FirstRunDiscovery
from dynamic_maintenance import DynamicMaintenance


class NewsWhitelistCLI:
    """新闻白名单命令行接口"""
    
    def __init__(self):
        self.whitelist_manager = WhitelistManager()
        self.discovery = FirstRunDiscovery()
        self.maintenance = DynamicMaintenance()
    
    async def handle_command(self, args):
        """处理命令"""
        if args.command == 'init':
            await self.cmd_init(args)
        elif args.command == 'test':
            await self.cmd_test(args)
        elif args.command == 'discover':
            await self.cmd_discover(args)
        elif args.command == 'add':
            await self.cmd_add(args)
        elif args.command == 'remove':
            await self.cmd_remove(args)
        elif args.command == 'list':
            await self.cmd_list(args)
        elif args.command == 'stats':
            await self.cmd_stats(args)
        elif args.command == 'refresh':
            await self.cmd_refresh(args)
        elif args.command == 'daily':
            await self.cmd_daily(args)
        elif args.command == 'suggest':
            await self.cmd_suggest(args)
        elif args.command == 'config':
            await self.cmd_config(args)
        else:
            print(f"未知命令: {args.command}")
            self.print_help()
    
    async def cmd_init(self, args):
        """初始化命令 - 首次运行自动发现"""
        print("=" * 60)
        print("首次运行初始化")
        print("=" * 60)
        
        keywords = args.keywords if args.keywords else []
        
        if not keywords and not args.skip_prompt:
            user_input = input("请输入关键词（用空格分隔，或直接回车使用默认）: ").strip()
            if user_input:
                keywords = user_input.split()
        
        print(f"使用关键词: {keywords if keywords else ['news', 'sports', 'technology']}")
        
        if not args.skip_confirm:
            confirm = input("开始自动发现新闻源? (y/n): ").strip().lower()
            if confirm != 'y':
                print("取消初始化")
                return
        
        print("\n开始自动发现...")
        discovered = await self.discovery.run_discovery(keywords)
        
        print("\n" + "=" * 60)
        if discovered > 0:
            print(f"✅ 初始化成功！发现了 {discovered} 个可用新闻源")
            self.discovery.print_discovery_summary()
        else:
            print("⚠️  初始化未发现可用新闻源")
            print("建议手动添加新闻源或提供更具体的关键词")
        
        print("=" * 60)
    
    async def cmd_test(self, args):
        """测试命令"""
        if args.all:
            print("测试所有活跃URL...")
            results = await self.whitelist_manager.test_all_active()
            print(f"测试完成，结果已保存")
        elif args.quick:
            print("快速测试...")
            results = await self.maintenance.quick_test()
            
            print(f"\n快速测试结果 ({len(results)} 个URL):")
            success_count = sum(1 for _, success, _ in results if success)
            print(f"成功: {success_count}, 失败: {len(results) - success_count}")
            
            for url, success, response_time in results:
                status = "✅" if success else "❌"
                print(f"  {status} {url} ({response_time}ms)")
        else:
            print("请指定测试模式: --all 或 --quick")
    
    async def cmd_discover(self, args):
        """发现新源命令"""
        keywords = args.keywords if args.keywords else []
        limit = args.limit
        
        print(f"发现新源 (关键词: {keywords}, 限制: {limit})...")
        discovered = await self.discovery.run_discovery(keywords)
        
        if discovered > 0:
            print(f"✅ 发现了 {discovered} 个新源")
            self.discovery.print_discovery_summary()
        else:
            print("⚠️  未发现新源")
    
    async def cmd_add(self, args):
        """添加URL命令"""
        url = args.url
        category = args.category
        
        # 检查URL格式
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        print(f"添加URL: {url} (分类: {category})")
        
        # 简单测试URL
        import aiohttp
        async with aiohttp.ClientSession() as session:
            success, response_time = await self.whitelist_manager.test_url(url, session)
        
        if success:
            # 添加到白名单
            source = {
                'url': url,
                'title': url.split('//')[-1].split('/')[0],
                'description': f'手动添加的新闻源 - {category}',
                'added_at': datetime.now().isoformat(),
                'last_tested': datetime.now().isoformat(),
                'success_count': 1,
                'failure_count': 0,
                'success_rate': 1.0,
                'last_response_time_ms': response_time,
                'usage_count': 0,
                'keywords': []
            }
            
            if category not in self.whitelist_manager.whitelist['active']:
                self.whitelist_manager.whitelist['active'][category] = []
            
            self.whitelist_manager.whitelist['active'][category].append(source)
            self.whitelist_manager.save_whitelist()
            
            print(f"✅ 已添加URL到 {category} 分类")
        else:
            print(f"❌ URL不可访问，添加失败")
    
    async def cmd_remove(self, args):
        """移除URL命令"""
        url = args.url
        
        removed = False
        for category in list(self.whitelist_manager.whitelist['active'].keys()):
            for i, source in enumerate(self.whitelist_manager.whitelist['active'][category]):
                if source['url'] == url:
                    # 移动到历史记录
                    self.whitelist_manager.whitelist['history']['removed'].append({
                        'url': url,
                        'removed_at': datetime.now().isoformat(),
                        'reason': '手动移除',
                        'previous_success_rate': source.get('success_rate', 0),
                        'category': category
                    })
                    
                    # 从活跃列表中移除
                    self.whitelist_manager.whitelist['active'][category].pop(i)
                    removed = True
                    break
            
            if removed:
                break
        
        if removed:
            self.whitelist_manager.save_whitelist()
            print(f"✅ 已移除URL: {url}")
        else:
            print(f"❌ 未找到URL: {url}")
    
    async def cmd_list(self, args):
        """列出URL命令"""
        category = args.category
        
        print("=" * 60)
        print("白名单URL列表")
        print("=" * 60)
        
        if category and category in self.whitelist_manager.whitelist['active']:
            sources = self.whitelist_manager.whitelist['active'][category]
            print(f"分类: {category} ({len(sources)} 个源)")
            print("-" * 40)
            
            for i, source in enumerate(sources, 1):
                success_rate = source.get('success_rate', 0) * 100
                print(f"{i}. {source['url']}")
                print(f"   成功率: {success_rate:.1f}%, 使用次数: {source.get('usage_count', 0)}")
                if source.get('last_tested'):
                    print(f"   最后测试: {source['last_tested'][:19]}")
                print()
        
        elif not category:
            total_count = 0
            for cat, sources in self.whitelist_manager.whitelist['active'].items():
                if sources:
                    print(f"{cat}: {len(sources)} 个源")
                    total_count += len(sources)
            
            print(f"\n总计: {total_count} 个活跃源")
        else:
            print(f"分类 '{category}' 不存在或为空")
        
        print("=" * 60)
    
    async def cmd_stats(self, args):
        """统计命令"""
        self.whitelist_manager.print_statistics()
    
    async def cmd_refresh(self, args):
        """刷新命令 - 全面测试+清理+发现"""
        print("=" * 60)
        print("刷新白名单")
        print("=" * 60)
        
        # 1. 测试所有活跃URL
        print("1. 测试所有活跃URL...")
        await self.whitelist_manager.test_all_active()
        
        # 2. 清理失败源
        print("2. 清理失败率过高的源...")
        removed = self.whitelist_manager.cleanup_failed_sources()
        print(f"   移除了 {removed} 个源")
        
        # 3. 发现新源（如果需要）
        active_count = sum(len(sources) for sources in self.whitelist_manager.whitelist['active'].values())
        if active_count < 15 or args.force_discover:
            print("3. 发现新源...")
            discovered = await self.discovery.run_discovery(
                self.whitelist_manager.whitelist['user_preferences']['frequent_keywords']
            )
            print(f"   发现了 {discovered} 个新源")
        else:
            print("3. 活跃源充足，跳过发现")
        
        print("\n" + "=" * 60)
        print("✅ 刷新完成")
        self.whitelist_manager.print_statistics()
        print("=" * 60)
    
    async def cmd_daily(self, args):
        """每日维护命令"""
        print("运行每日维护...")
        await self.maintenance.run_daily_maintenance()
        self.maintenance.print_maintenance_summary()
    
    async def cmd_suggest(self, args):
        """建议命令"""
        keyword = args.keyword
        suggestions = self.maintenance.get_url_suggestions(keyword)
        
        print(f"关键词 '{keyword}' 的建议:")
        print("-" * 40)
        
        if suggestions:
            for i, url in enumerate(suggestions, 1):
                print(f"{i}. {url}")
        else:
            print("暂无建议")
        
        print("-" * 40)
    
    async def cmd_config(self, args):
        """配置命令"""
        if args.show:
            print("当前配置:")
            print("-" * 40)
            for key, value in self.whitelist_manager.whitelist['config'].items():
                print(f"{key}: {value}")
            print("-" * 40)
        
        elif args.set:
            if len(args.set) == 2:
                key, value = args.set
                
                # 类型转换
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                elif value.isdigit():
                    value = int(value)
                elif value.replace('.', '', 1).isdigit():
                    value = float(value)
                
                if key in self.whitelist_manager.whitelist['config']:
                    self.whitelist_manager.whitelist['config'][key] = value
                    self.whitelist_manager.save_whitelist()
                    print(f"✅ 已设置 {key} = {value}")
                else:
                    print(f"❌ 未知配置项: {key}")
            else:
                print("❌ 格式错误，使用: --set key value")
    
    def print_help(self):
        """打印帮助信息"""
        help_text = """
新闻白名单管理工具

命令:
  init             首次运行初始化，自动发现新闻源
  test             测试URL可访问性
  discover         发现新新闻源
  add              手动添加URL到白名单
  remove           从白名单移除URL
  list             列出白名单URL
  stats            显示统计信息
  refresh          刷新白名单（测试+清理+发现）
  daily            运行每日维护
  suggest          根据关键词建议URL
  config           管理配置
  cleanup          清理技能目录临时文件（磁盘空间）

示例:
  python cli.py init --keywords "sports badminton"
  python cli.py test --all
  python cli.py add --url https://example.com --category news
  python cli.py list --category sports
  python cli.py refresh
  python cli.py suggest --keyword technology
  python cli.py cleanup
  python cli.py cleanup --prune-whitelist-history
        """
        print(help_text)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="新闻白名单管理工具")
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # init 命令
    init_parser = subparsers.add_parser('init', help='首次运行初始化')
    init_parser.add_argument('--keywords', nargs='+', help='关键词列表')
    init_parser.add_argument('--skip-prompt', action='store_true', help='跳过关键词提示')
    init_parser.add_argument('--skip-confirm', action='store_true', help='跳过确认')
    
    # test 命令
    test_parser = subparsers.add_parser('test', help='测试URL')
    test_group = test_parser.add_mutually_exclusive_group(required=True)
    test_group.add_argument('--all', action='store_true', help='测试所有URL')
    test_group.add_argument('--quick', action='store_true', help='快速测试')
    
    # discover 命令
    discover_parser = subparsers.add_parser('discover', help='发现新源')
    discover_parser.add_argument('--keywords', nargs='+', help='关键词列表')
    discover_parser.add_argument('--limit', type=int, default=10, help='发现数量限制')
    
    # add 命令
    add_parser = subparsers.add_parser('add', help='添加URL')
    add_parser.add_argument('--url', required=True, help='URL地址')
    add_parser.add_argument('--category', default='general', help='分类')
    
    # remove 命令
    remove_parser = subparsers.add_parser('remove', help='移除URL')
    remove_parser.add_argument('--url', required=True, help='URL地址')
    
    # list 命令
    list_parser = subparsers.add_parser('list', help='列出URL')
    list_parser.add_argument('--category', help='指定分类')
    
    # stats 命令
    subparsers.add_parser('stats', help='显示统计')
    
    # refresh 命令
    refresh_parser = subparsers.add_parser('refresh', help='刷新白名单')
    refresh_parser.add_argument('--force-discover', action='store_true', help='强制发现新源')
    
    # daily 命令
    subparsers.add_parser('daily', help='每日维护')
    
    # suggest 命令
    suggest_parser = subparsers.add_parser('suggest', help='建议URL')
    suggest_parser.add_argument('--keyword', required=True, help='关键词')
    
    # config 命令
    config_parser = subparsers.add_parser('config', help='管理配置')
    config_group = config_parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument('--show', action='store_true', help='显示配置')
    config_group.add_argument('--set', nargs=2, metavar=('KEY', 'VALUE'), help='设置配置')

    # cleanup 命令（同步子进程，见 skill_cleanup.py）
    cleanup_parser = subparsers.add_parser('cleanup', help='清理技能目录内临时文件（见 SKILL.md §13）')
    cleanup_parser.add_argument('--dry-run', action='store_true', help='仅打印将删除的路径')
    cleanup_parser.add_argument(
        '--prune-whitelist-history',
        action='store_true',
        help='清空 whitelist.json 中 history.test_log 与 history.removed',
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    if args.command == 'cleanup':
        import subprocess

        script = Path(__file__).resolve().parent / 'skill_cleanup.py'
        cmd = [sys.executable, str(script)]
        if args.dry_run:
            cmd.append('--dry-run')
        if args.prune_whitelist_history:
            cmd.append('--prune-whitelist-history')
        raise SystemExit(subprocess.call(cmd))
    
    cli = NewsWhitelistCLI()
    asyncio.run(cli.handle_command(args))


if __name__ == "__main__":
    main()