FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
RUN useradd --create-home mypath
USER mypath
EXPOSE 8000
CMD ["waitress-serve", "--host=0.0.0.0", "--port=8000", "--call", "app:create_app"]
