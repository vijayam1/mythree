# Mythree on Hugging Face Spaces (or any host that runs a container).
# Keys, the passcode, voice IDs and the phrase book come from the host's
# secret store as environment variables, never from files in this image.
FROM python:3.13-slim

RUN useradd --create-home mythree
WORKDIR /home/mythree/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

USER mythree
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
