#!/usr/bin/env python3
"""
白名单管理器核心类
实现动态白名单的维护、测试和发现功能
"""

import json
import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WhitelistManager:
    """白名单管理器"""
    
    def __init__(self, config_path: str = "config/whitelist.json"):
        self.config_path = Path(config_path)
        self.whitelist = self._load_whitelist()
        self.session = None
        self.test_cache = {}
        
    def _load_whitelist(self) -> Dict:
        """加载白名单配置"""
        if not self.config_path.exists():
            logger.warning(f"白名单配置文件不存在: {self.config_path}")
            return self._create_default_whitelist()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"已加载白名单配置，版本: {data.get('version', '未知')}")
                return data
        except Exception as e:
            logger.error(f"加载白名单配置失败: {e}")
            return self._create_default_whitelist()
    
    def _create_default_whitelist(self) -> Dict:
        """创建默认白名单配置"""
        return {
            "version": "2.0",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "last_full_test": None,
            "config": {
                "test_concurrency": 10,
                "test_timeout_seconds": 5,
                "cache_ttl_seconds": 3600,
                "failure_threshold": 3,
                "min_success_rate": 0.7,
                "auto_discovery_enabled": True,
                "daily_test_enabled": True
            },
            "active": {},
            "history": {
                "removed": [],
                "test_log": []
            },
            "statistics": {
                "total_active_sources": 0,
                "total_tests": 0,
                "successful_tests": 0,
                "failed_tests": 0,
                "overall_success_rate": 0.0,
                "average_response_time_ms": 0
            },
            "user_preferences": {
                "frequent_keywords": [],
                "preferred_categories": [],
                "custom_sources": []
            }
        }
    
    def save_whitelist(self):
        """保存白名单配置"""
        self.whitelist['last_updated'] = datetime.now().isoformat()
        
        # 确保目录存在
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.whitelist, f, indent=2, ensure_ascii=False)
            logger.info(f"白名单配置已保存: {self.config_path}")
        except Exception as e:
            logger.error(f"保存白名单配置失败: {e}")
    
    async def test_url(self, url: str, session: aiohttp.ClientSession) -> Tuple[bool, Optional[int]]:
        """测试单个URL的可访问性"""
        cache_key = f"{url}_{int(time.time() // self.whitelist['config']['cache_ttl_seconds'])}"
        
        # 检查缓存
        if cache_key in self.test_cache:
            return self.test_cache[cache_key]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        start_time = time.time()
        try:
            async with session.get(
                url, 
                headers=headers, 
                timeout=aiohttp.ClientTimeout(total=self.whitelist['config']['test_timeout_seconds']),
                allow_redirects=True
            ) as response:
                response_time = int((time.time() - start_time) * 1000)
                
                # 检查响应状态
                if response.status == 200:
                    # 简单的内容检查（可选）
                    content_type = response.headers.get('Content-Type', '')
                    if 'text/html' in content_type or 'application/json' in content_type:
                        result = (True, response_time)
                    else:
                        result = (False, response_time)
                else:
                    result = (False, response_time)
                
                self.test_cache[cache_key] = result
                return result
                
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            logger.debug(f"测试URL失败 {url}: {e}")
            result = (False, response_time)
            self.test_cache[cache_key] = result
            return result
    
    async def test_category(self, category: str, urls: List[Dict]) -> List[Dict]:
        """测试一个分类下的所有URL"""
        if not urls:
            return []
        
        logger.info(f"开始测试分类: {category}, URL数量: {len(urls)}")
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for source in urls:
                task = self.test_url(source['url'], session)
                tasks.append((source, task))
            
            # 限制并发数
            concurrency = self.whitelist['config']['test_concurrency']
            results = []
            
            for i in range(0, len(tasks), concurrency):
                batch = tasks[i:i+concurrency]
                batch_tasks = [task for _, task in batch]
                batch_sources = [source for source, _ in batch]
                
                batch_results = await asyncio.gather(*batch_tasks)
                
                for source, (success, response_time) in zip(batch_sources, batch_results):
                    # 更新统计
                    source['last_tested'] = datetime.now().isoformat()
                    
                    if success:
                        source['success_count'] += 1
                        source['last_response_time_ms'] = response_time
                    else:
                        source['failure_count'] += 1
                    
                    # 计算成功率
                    total = source['success_count'] + source['failure_count']
                    source['success_rate'] = source['success_count'] / total if total > 0 else 0.0
                    
                    # 更新全局统计
                    self.whitelist['statistics']['total_tests'] += 1
                    if success:
                        self.whitelist['statistics']['successful_tests'] += 1
                    else:
                        self.whitelist['statistics']['failed_tests'] += 1
                    
                    results.append(source)
                    
                    # 记录测试日志
                    self.whitelist['history']['test_log'].append({
                        'timestamp': datetime.now().isoformat(),
                        'url': source['url'],
                        'success': success,
                        'response_time_ms': response_time,
                        'category': category
                    })
            
            return results
    
    async def test_all_active(self) -> Dict[str, List[Dict]]:
        """测试所有活跃的白名单URL"""
        logger.info("开始测试所有活跃白名单URL")
        
        results = {}
        for category, sources in self.whitelist['active'].items():
            if sources:
                tested_sources = await self.test_category(category, sources)
                results[category] = tested_sources
        
        # 更新统计
        total_sources = sum(len(sources) for sources in self.whitelist['active'].values())
        successful_tests = self.whitelist['statistics']['successful_tests']
        total_tests = self.whitelist['statistics']['total_tests']
        
        if total_tests > 0:
            self.whitelist['statistics']['overall_success_rate'] = successful_tests / total_tests
        
        self.whitelist['last_full_test'] = datetime.now().isoformat()
        self.save_whitelist()
        
        logger.info(f"测试完成，总测试数: {total_tests}, 成功率: {self.whitelist['statistics']['overall_success_rate']:.2%}")
        return results
    
    def cleanup_failed_sources(self):
        """清理失败次数过多的源"""
        removed_count = 0
        
        for category in list(self.whitelist['active'].keys()):
            active_sources = []
            for source in self.whitelist['active'][category]:
                total = source['success_count'] + source['failure_count']
                
                if total >= self.whitelist['config']['failure_threshold']:
                    success_rate = source['success_count'] / total
                    
                    if success_rate < self.whitelist['config']['min_success_rate']:
                        # 移动到历史记录
                        self.whitelist['history']['removed'].append({
                            'url': source['url'],
                            'removed_at': datetime.now().isoformat(),
                            'reason': f'成功率过低: {success_rate:.2%}',
                            'previous_success_rate': success_rate,
                            'success_count': source['success_count'],
                            'failure_count': source['failure_count'],
                            'category': category
                        })
                        removed_count += 1
                        logger.info(f"移除URL: {source['url']}, 成功率: {success_rate:.2%}")
                        continue
                
                active_sources.append(source)
            
            self.whitelist['active'][category] = active_sources
        
        if removed_count > 0:
            self.save_whitelist()
            logger.info(f"已移除 {removed_count} 个失败率过高的源")
        
        return removed_count
    
    def add_user_keyword(self, keyword: str):
        """添加用户关键词"""
        if keyword not in self.whitelist['user_preferences']['frequent_keywords']:
            self.whitelist['user_preferences']['frequent_keywords'].append(keyword)
            self.save_whitelist()
            logger.info(f"已添加用户关键词: {keyword}")
    
    def get_recommended_urls(self, keyword: str) -> List[str]:
        """根据关键词推荐URL"""
        # 这里可以扩展为更智能的推荐算法
        # 目前简单返回空列表，后续可以集成搜索引擎或预设库
        return []
    
    def print_statistics(self):
        """打印统计信息"""
        stats = self.whitelist['statistics']
        active_sources = sum(len(sources) for sources in self.whitelist['active'].values())
        
        print("=" * 50)
        print("白名单统计信息")
        print("=" * 50)
        print(f"活跃源数量: {active_sources}")
        print(f"总测试次数: {stats['total_tests']}")
        print(f"成功测试: {stats['successful_tests']}")
        print(f"失败测试: {stats['failed_tests']}")
        print(f"总体成功率: {stats['overall_success_rate']:.2%}")
        print(f"平均响应时间: {stats['average_response_time_ms']:.0f} ms")
        
        if self.whitelist['last_full_test']:
            print(f"最后完整测试: {self.whitelist['last_full_test']}")
        
        print(f"用户关键词: {', '.join(self.whitelist['user_preferences']['frequent_keywords'][:10])}")
        print("=" * 50)


async def main():
    """主函数"""
    manager = WhitelistManager()
    
    print("白名单管理器启动")
    print(f"配置文件: {manager.config_path}")
    
    # 测试所有活跃URL
    print("\n开始测试所有活跃URL...")
    results = await manager.test_all_active()
    
    # 清理失败源
    print("\n清理失败率过高的源...")
    removed = manager.cleanup_failed_sources()
    print(f"已移除 {removed} 个源")
    
    # 显示统计
    manager.print_statistics()


if __name__ == "__main__":
    asyncio.run(main())