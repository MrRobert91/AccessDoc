FROM python:3.12-slim

# System deps: tesseract, java (for veraPDF), poppler
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    openjdk-21-jre-headless \
    curl \
    unzip \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install veraPDF
RUN curl -L https://github.com/veraPDF/veraPDF-apps/releases/download/v1.26.2/verapdf-installer-1.26.2.zip \
    -o /tmp/verapdf.zip \
    && unzip /tmp/verapdf.zip -d /tmp/verapdf_install \
    && chmod +x /tmp/verapdf_install/verapdf-installer-1.26.2/*.sh \
    && /tmp/verapdf_install/verapdf-installer-1.26.2/verapdf_installer.sh -console \
    -DautoInstallPath=/usr/local/verapdf \
    || true \
    && ln -sf /usr/local/verapdf/verapdf /usr/local/bin/verapdf \
    && rm -rf /tmp/verapdf.zip /tmp/verapdf_install

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/accessdoc

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
