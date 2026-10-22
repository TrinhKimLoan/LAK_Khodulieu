FIXED archive structure. Copy/merge the app and tests directories DIRECTLY into D:\vietnam_ecom_dwh_project (not into nested ecom_relevance_v31_patch).
Reason old ZIP did not work: it had one extra enclosing folder.
PowerShell from project root:
  Copy-Item .\app\relevance.py .\app\relevance_before_v31.py
  # Now overwrite .\app\relevance.py with file from this archive, under app\relevance.py
  Select-String .\app\relevance.py -Pattern 'camera kép|oppo|OUT_OF_SCOPE_CONTEXT'
  docker compose --profile tools build --no-cache pipeline
  docker compose --profile tools run --rm --entrypoint python pipeline -c "from app.relevance import classify; print(classify('OPPO Find X10 Series chuẩn bị ra mắt tại Việt Nam cùng camera kép 200MP và Sơn Tùng M-TP'))"
  docker compose --profile tools run --rm pipeline python -m app.cli reclassify-news
  docker compose --profile tools run --rm pipeline python -m app.cli marts
  docker compose --profile tools run --rm pipeline python -m app.cli validate
No migrations or backfill needed.
