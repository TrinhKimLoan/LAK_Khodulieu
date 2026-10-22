from app.core import ingest_news

test_articles = [
    {
        "id": "cdc-demo-001",
        "title": "Giá RAM DDR5 cho PC tăng mạnh",
        "url": "https://example.invalid/cdc-demo-ram-ddr5-001",
        "publish_date": "2025-05-12",
        "media_url": "example.invalid",
    }
]

ingest_news(test_articles, "cdc_demo")