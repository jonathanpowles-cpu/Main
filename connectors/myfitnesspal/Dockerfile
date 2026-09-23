# Build from the repository root:
#   docker build -f connectors/myfitnesspal/Dockerfile -t mfp-connector .
#   docker run -p 8000:8000 -e CONNECTOR_PASSWORD=... -e PUBLIC_URL=https://... -e MFP_COOKIE_HEADER=... mfp-connector
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY connectors/ connectors/
ENV PORT=8000
EXPOSE 8000
CMD ["python", "-m", "connectors.myfitnesspal", "serve", "--transport", "http"]
