FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "mcp>=1.28,<2"
COPY server.py ./server.py
EXPOSE 8765
CMD ["python", "server.py"]
