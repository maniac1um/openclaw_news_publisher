#!/usr/bin/env python3
"""
动态维护模块
实现白名单的日常维护、动态发现和清理功能
"""

import json
import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from .whitelist_manager import WhitelistManager
from .first_run_discovery import FirstRunDiscovery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DynamicMaintenance:
    """动态维护管理器"""
    
    def __init__(self):
        self.whitelist_manager = WhitelistManager()
        self.discovery = FirstRunDiscovery()
        self.maintenance_log = []
        
    def should_run_daily_test(self) -> bool:
        """判断是否应该运行每日测试"""
        if not self.whitelist_manager.whitelist['config']['daily_test_enabled']:
            return False
        
        last_test = self.whitelist_manager.whitelist['last_full_test']
        if not last_test:
            return True
        
        try:
            last_test_time = datetime.fromisoformat(last_test.replace('Z', '+00:00'))
            now = datetime.now()
            
            # 如果超过24小时，运行测试
            return (now - last_test_time) > timedelta(hours=24)
        except:
            return True
    
    async def run_daily_maintenance(self):
        """运行每日维护"""
        logger.info("开始每日维护")
        
        # 1. 测试所有活跃URL
        logger.info("步骤1: 测试所有活跃URL")
        await self.whitelist_manager.test_all_active()
        
        # 2. 清理失败源
        logger.info("步骤2: 清理失败率过高的源")
        removed_count = self.whitelist_manager.cleanup_failed_sources()
        
        # 3. 检查是否需要补充源
        active_count = sum(len(sources) for sources in self.whitelist_manager.whitelist['active'].values())
        if active_count < 10:  # 如果活跃源太少
            logger.info(f"活跃源不足 ({active_count}个)，尝试发现新源")
            await self.discover_new_sources()
        
        # 4. 更新用户偏好
        self.update_user_preferences()
        
        # 记录维护日志
        self.maintenance_log.append({
            'timestamp': datetime.now().isoformat(),
            'action': 'daily_maintenance',
            'active_sources': active_count,
            'removed_sources': removed_count,
            'new_sources_discovered': 0  # 可以在discover_new_sources中更新
        })
        
        logger.info(f"每日维护完成，移除了 {removed_count} 个源")
    
    async def discover_new_sources(self, limit: int = 10):
        """发现新源"""
        if not self.whitelist_manager.whitelist['config']['auto_discovery_enabled']:
            logger.info("自动发现已禁用")
            return 0
        
        # 获取用户常用关键词
        user_keywords = self.whitelist_manager.whitelist['user_preferences']['frequent_keywords']
        
        if not user_keywords:
            logger.info("没有用户关键词，使用通用发现")
            user_keywords = ['news', 'sports', 'technology']  # 默认关键词
        
        logger.info(f"基于用户关键词发现新源: {user_keywords}")
        
        # 使用首次发现模块
        discovered = await self.discovery.run_discovery(user_keywords)
        
        # 记录到维护日志
        if discovered > 0:
            if self.maintenance_log and self.maintenance_log[-1]['action'] == 'daily_maintenance':
                self.maintenance_log[-1]['new_sources_discovered'] = discovered
        
        return discovered
    
    def update_user_preferences(self):
        """更新用户偏好"""
        # 分析使用模式，更新用户偏好
        # 这里可以扩展为更复杂的分析逻辑
        
        # 简单示例：统计最常用的分类
        category_usage = {}
        for category, sources in self.whitelist_manager.whitelist['active'].items():
            total_usage = sum(source.get('usage_count', 0) for source in sources)
            if total_usage > 0:
                category_usage[category] = total_usage
        
        # 更新首选分类
        if category_usage:
            preferred = sorted(category_usage.items(), key=lambda x: x[1], reverse=True)[:3]
            self.whitelist_manager.whitelist['user_preferences']['preferred_categories'] = [
                cat for cat, _ in preferred
            ]
        
        # 保存更新
        self.whitelist_manager.save_whitelist()
    
    def get_url_suggestions(self, keyword: str) -> List[str]:
        """获取URL建议"""
        suggestions = []
        
        # 1. 从白名单中推荐
        for category, sources in self.whitelist_manager.whitelist['active'].items():
            for source in sources:
                if keyword.lower() in ' '.join(source.get('keywords', [])).lower():
                    suggestions.append(source['url'])
        
        # 2. 从历史记录中恢复
        for removed in self.whitelist_manager.whitelist['history']['removed']:
            if (removed.get('previous_success_rate', 0) > 0.8 and 
                keyword.lower() in removed.get('url', '').lower()):
                suggestions.append(removed['url'])
        
        # 去重并限制数量
        suggestions = list(set(suggestions))[:10]
        return suggestions
    
    async def quick_test(self, urls: List[str] = None) -> List[Tuple[str, bool, int]]:
        """快速测试一批URL"""
        if urls is None:
            # 测试最近使用或高成功率的URL
            urls = []
            for category, sources in self.whitelist_manager.whitelist['active'].items():
                # 按成功率排序，取前5个
                sorted_sources = sorted(sources, key=lambda x: x.get('success_rate', 0), reverse=True)
                urls.extend([s['url'] for s in sorted_sources[:5]])
        
        urls = list(set(urls))[:20]  # 限制数量
        
        results = []
        async with aiohttp.ClientSession() as session:
            for url in urls:
                success, response_time = await self.whitelist_manager.test_url(url, session)
                results.append((url, success, response_time))
        
        return results
    
    def export_maintenance_report(self) -> Dict:
        """导出维护报告"""
        active_count = sum(len(sources) for sources in self.whitelist_manager.whitelist['active'].values())
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'active_sources': active_count,
            'statistics': self.whitelist_manager.whitelist['statistics'].copy(),
            'recent_maintenance': self.maintenance_log[-5:] if self.maintenance_log else [],
            'recommendations': []
        }
        
        # 生成建议
        overall_rate = self.whitelist_manager.whitelist['statistics']['overall_success_rate']
        if overall_rate < 0.5:
            report['recommendations'].append('总体成功率较低，建议运行全面测试')
        
        if active_count < 5:
            report['recommendations'].append('活跃源数量不足，建议发现新源')
        
        return report
    
    def print_maintenance_summary(self):
        """打印维护摘要"""
        print("=" * 50)
        print("动态维护摘要")
        print("=" * 50)
        
        # 显示统计
        self.whitelist_manager.print_statistics()
        
        # 显示最近维护
        if self.maintenance_log:
            print("\n最近维护记录:")
            for log in self.maintenance_log[-3:]:
                print(f"  {log['timestamp']}: {log['action']}")
                if 'removed_sources' in log:
                    print(f"    移除了 {log['removed_sources']} 个源")
                if 'new_sources_discovered' in log:
                    print(f"    发现了 {log['new_sources_discovered']} 个新源")
        
        # 显示建议
        report = self.export_maintenance_report()
        if report['recommendations']:
            print("\n建议:")
            for rec in report['recommendations']:
                print(f"  • {rec}")
        
        print("=" * 50)


async def main():
    """主函数"""
    import sys
    
    maintenance = DynamicMaintenance()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'daily':
            # 运行每日维护
            await maintenance.run_daily_maintenance()
            maintenance.print_maintenance_summary()
            
        elif command == 'quick-test':
            # 快速测试
            print("运行快速测试...")
            results = await maintenance.quick_test()
            
            print(f"测试了 {len(results)} 个URL:")
            for url, success, response_time in results:
                status = "✅" if success else "❌"
                print(f"  {status} {url} ({response_time}ms)")
            
        elif command == 'discover':
            # 发现新源
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            print(f"发现新源 (限制: {limit})...")
            discovered = await maintenance.discover_new_sources(limit)
            print(f"发现了 {discovered} 个新源")
            
        elif command == 'suggest':
            # 获取建议
            keyword = sys.argv[2] if len(sys.argv) > 2 else 'news'
            suggestions = maintenance.get_url_suggestions(keyword)
            
            print(f"关键词 '{keyword}' 的建议URL:")
            for i, url in enumerate(suggestions, 1):
                print(f"  {i}. {url}")
            
        elif command == 'report':
            # 导出报告
            report = maintenance.export_maintenance_report()
            print(json.dumps(report, indent=2, ensure_ascii=False))
            
        else:
            print(f"未知命令: {command}")
            print("可用命令: daily, quick-test, discover, suggest, report")
    
    else:
        # 交互模式
        print("动态维护管理器")
        print("=" * 30)
        
        if maintenance.should_run_daily_test():
            print("检测到需要运行每日维护")
            response = input("是否运行每日维护? (y/n): ")
            if response.lower() == 'y':
                await maintenance.run_daily_maintenance()
                maintenance.print_maintenance_summary()
        else:
            print("今日已运行过维护")
            maintenance.print_maintenance_summary()


if __name__ == "__main__":
    asyncio.run(main())