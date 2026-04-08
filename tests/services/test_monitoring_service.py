from app.services.monitoring_service import MonitoringService


def test_generate_candidate_urls_count_and_platforms() -> None:
    urls = MonitoringService.generate_candidate_urls(
        keyword="羽毛球价格",
        count=20,
        platforms=["taobao", "tmall", "jd", "news"],
    )
    assert len(urls) == 20
    assert all(item[1].startswith("http") for item in urls)
    assert any(item[0] == "taobao" for item in urls)
    assert any(item[0] == "tmall" for item in urls)
    assert any(item[0] == "jd" for item in urls)


def test_generate_candidate_urls_with_small_platform_set() -> None:
    urls = MonitoringService.generate_candidate_urls(
        keyword="羽毛球",
        count=7,
        platforms=["jd"],
    )
    assert len(urls) == 7
    assert all(item[0] == "jd" for item in urls)


def test_extract_price_from_html_variants() -> None:
    price1, _ = MonitoringService._extract_price("<div>活动价 ¥99.50 包邮</div>", platform="jd")
    price2, _ = MonitoringService._extract_price("<span>到手价 88元</span>", platform="taobao")
    price3, _ = MonitoringService._extract_price("<html>no price</html>", platform="news")
    assert price1 == 99.5
    assert price2 == 88.0
    assert price3 is None


def test_extract_price_platform_specific_candidates() -> None:
    html = '{"view_price":"129.00","reserve_price":"139.00","other":"x"}'
    price, candidates = MonitoringService._extract_price(html, platform="taobao")
    assert price == 129.0
    assert 129.0 in candidates
