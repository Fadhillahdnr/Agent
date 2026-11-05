FROM python:3.12-slim
WORKDIR /srv
COPY src ./src
ENV PAYMENT_GATEWAY_URL=http://pay.local
CMD ["python", "-m", "src.orders"]
