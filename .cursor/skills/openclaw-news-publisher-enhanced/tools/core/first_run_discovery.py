#!/usr/bin/env python3
"""
首次运行自动发现模块
用于skill首次运行时自动发现可用的新闻源
"""

import json
import asyncio
import aiohttp
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from .whitelist_manager import WhitelistManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FirstRunDiscovery:
    """首次运行自动发现"""
    
    def __init__(self, seed_config_path: str = "config/seed_urls.json"):
        self.seed_config_path = Path(seed_config_path)
        self.seed_config = self._load_seed_config()
        self.whitelist_manager = WhitelistManager()
        self.discovered_urls = []
        
    def _load_seed_config(self) -> Dict:
        """加载种子配置"""
        if not self.seed_config_path.exists():
            logger.warning(f"种子配置文件不存在: {self.seed_config_path}")
            return self._create_default_seed_config()
        
        try:
            with open(self.seed_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载种子配置失败: {e}")
            return self._create_default_seed_config()
    
    def _create_default_seed_config(self) -> Dict:
        """创建默认种子配置"""
        return {
            "categories": {
                "general": {
                    "domains": ["cnn", "bbc", "reuters", "apnews"],
                    "url_patterns": ["https://www.{domain}.com", "https://{domain}.com"]
                }
            }
        }
    
    def generate_test_urls(self, user_keywords: List[str] = None) -> List[str]:
        """根据用户关键词生成测试URL"""
        if user_keywords is None:
            user_keywords = []
        
        test_urls = []
        
        # 1. 首先尝试通用新闻源
        if "general" in self.seed_config["categories"]:
            general_config = self.seed_config["categories"]["general"]
            for domain in general_config.get("domains", [])[:5]:  # 限制数量
                for pattern in general_config.get("url_patterns", []):
                    url = pattern.format(domain=domain)
                    test_urls.append(url)
        
        # 2. 根据用户关键词匹配分类
        keyword_to_category = {}
        for category, config in self.seed_config["categories"].items():
            if category == "general":
                continue
            
            keywords = config.get("keywords", [])
            for keyword in user_keywords:
                if any(kw in keyword.lower() for kw in keywords):
                    keyword_to_category[keyword] = category
                    break
        
        # 3. 为匹配的分类生成URL
        for keyword, category in keyword_to_category.items():
            if category in self.seed_config["categories"]:
                config = self.seed_config["categories"][category]
                for domain in config.get("domains", [])[:3]:  # 每个分类限制数量
                    for pattern in config.get("url_patterns", []):
                        url = pattern.format(domain=domain)
                        test_urls.append(url)
        
        # 去重
        test_urls = list(set(test_urls))
        logger.info(f"生成了 {len(test_urls)} 个测试URL")
        return test_urls
    
    async def test_url_batch(self, urls: List[str], session: aiohttp.ClientSession) -> List[Tuple[str, bool, int]]:
        """测试一批URL"""
        results = []
        
        for url in urls:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                start_time = time.time()
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=True
                ) as response:
                    response_time = int((time.time() - start_time) * 1000)
                    
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'text/html' in content_type or 'application/json' in content_type:
                            results.append((url, True, response_time))
                        else:
                            results.append((url, False, response_time))
                    else:
                        results.append((url, False, response_time))
                        
            except Exception as e:
                response_time = int((time.time() - start_time) * 1000)
                results.append((url, False, response_time))
                logger.debug(f"测试失败 {url}: {e}")
        
        return results
    
    def categorize_url(self, url: str) -> Optional[str]:
        """根据URL判断分类"""
        url_lower = url.lower()
        
        # 简单分类逻辑，可以根据需要扩展
        sports_keywords = ['sports', 'espn', 'nba', 'nfl', 'premierleague', 'badminton']
        tech_keywords = ['tech', 'crunch', 'verge', 'wired', 'arstechnica']
        news_keywords = ['news', 'cnn', 'bbc', 'reuters', 'apnews']
        finance_keywords = ['bloomberg', 'reuters', 'wsj', 'ft', 'finance']
        
        if any(keyword in url_lower for keyword in sports_keywords):
            return 'sports'
        elif any(keyword in url_lower for keyword in tech_keywords):
            return 'tech'
        elif any(keyword in url_lower for keyword in news_keywords):
            return 'news'
        elif any(keyword in url_lower for keyword in finance_keywords):
            return 'finance'
        else:
            return 'general'
    
    def add_to_whitelist(self, url: str, success: bool, response_time: int):
        """将URL添加到白名单"""
        if not success:
            return False
        
        category = self.categorize_url(url)
        
        # 检查是否已存在
        for cat in self.whitelist_manager.whitelist['active']:
            for source in self.whitelist_manager.whitelist['active'].get(cat, []):
                if source['url'] == url:
                    return False
        
        # 创建新的源记录
        source = {
            'url': url,
            'title': url.split('//')[-1].split('/')[0],
            'description': f'自动发现的新闻源 - {category}',
            'added_at': datetime.now().isoformat(),
            'last_tested': datetime.now().isoformat(),
            'success_count': 1,
            'failure_count': 0,
            'success_rate': 1.0,
            'last_response_time_ms': response_time,
            'usage_count': 0,
            'keywords': []
        }
        
        # 添加到对应分类
        if category not in self.whitelist_manager.whitelist['active']:
            self.whitelist_manager.whitelist['active'][category] = []
        
        self.whitelist_manager.whitelist['active'][category].append(source)
        self.discovered_urls.append(url)
        
        # 更新统计
        self.whitelist_manager.whitelist['statistics']['total_active_sources'] += 1
        
        return True
    
    async def run_discovery(self, user_keywords: List[str] = None):
        """运行自动发现"""
        if user_keywords is None:
            user_keywords = []
        
        logger.info("开始首次运行自动发现")
        logger.info(f"用户关键词: {user_keywords}")
        
        # 生成测试URL
        test_urls = self.generate_test_urls(user_keywords)
        
        if not test_urls:
            logger.warning("没有生成测试URL")
            return
        
        # 测试URL
        async with aiohttp.ClientSession() as session:
            # 分批测试，避免并发过高
            batch_size = 10
            discovered_count = 0
            
            for i in range(0, len(test_urls), batch_size):
                batch = test_urls[i:i+batch_size]
                logger.info(f"测试批次 {i//batch_size + 1}: {len(batch)} 个URL")
                
                results = await self.test_url_batch(batch, session)
                
                for url, success, response_time in results:
                    if self.add_to_whitelist(url, success, response_time):
                        discovered_count += 1
                        logger.info(f"发现可用源: {url} ({response_time}ms)")
                    else:
                        logger.debug(f"源不可用或已存在: {url}")
                
                # 短暂延迟，避免对目标网站造成负担
                await asyncio.sleep(1)
        
        # 保存白名单
        if discovered_count > 0:
            self.whitelist_manager.save_whitelist()
            logger.info(f"自动发现完成，发现了 {discovered_count} 个可用新闻源")
        else:
            logger.warning("自动发现未发现任何可用新闻源")
        
        return discovered_count
    
    def print_discovery_summary(self):
        """打印发现摘要"""
        print("=" * 50)
        print("首次运行自动发现摘要")
        print("=" * 50)
        
        if not self.discovered_urls:
            print("未发现任何可用新闻源")
        else:
            print(f"发现了 {len(self.discovered_urls)} 个可用新闻源:")
            for i, url in enumerate(self.discovered_urls[:20], 1):  # 限制显示数量
                print(f"  {i}. {url}")
            
            if len(self.discovered_urls) > 20:
                print(f"  ... 还有 {len(self.discovered_urls) - 20} 个")
        
        # 显示分类统计
        print("\n按分类统计:")
        for category, sources in self.whitelist_manager.whitelist['active'].items():
            if sources:
                print(f"  {category}: {len(sources)} 个源")
        
        print("=" * 50)


async def main():
    """主函数"""
    import sys
    
    # 从命令行参数获取用户关键词
    user_keywords = sys.argv[1:] if len(sys.argv) > 1 else []
    
    discovery = FirstRunDiscovery()
    
    print("首次运行自动发现启动")
    print(f"用户关键词: {user_keywords}")
    
    # 运行发现
    discovered = await discovery.run_discovery(user_keywords)
    
    # 显示摘要
    discovery.print_discovery_summary()
    
    if discovered > 0:
        print(f"\n✅ 自动发现成功！发现了 {discovered} 个可用新闻源")
        print("白名单已保存，skill现在可以正常使用")
    else:
        print("\n⚠️  自动发现未找到可用新闻源")
        print("建议：")
        print("  1. 检查网络连接")
        print("  2. 提供更具体的关键词")
        print("  3. 手动添加新闻源")


if __name__ == "__main__":
    asyncio.run(main())