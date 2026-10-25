FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY product_prices_v7.py .
COPY health_v6.py .
COPY health_local.py .
COPY shipping_options.py .
COPY health_features.py .
COPY warehouse_extra.py .
COPY ml_api.py .
COPY ml_outputs ./ml_outputs
COPY static ./static
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
