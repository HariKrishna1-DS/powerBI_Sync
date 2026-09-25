# Use official Python 3.11 slim image
FROM python:3.11-slim

# Install Chromium, Node.js, and Puppeteer dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    chromium \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    --no-install-recommends \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt-get/lists/*

# Puppeteer environment overrides for system Chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV DATATRACE_HEADLESS=true

WORKDIR /app

# Copy dependency files
COPY gsheet_dashboard/requirements.txt ./gsheet_dashboard/requirements.txt
COPY gsheet_dashboard/package.json gsheet_dashboard/package-lock.json* ./gsheet_dashboard/
COPY gsheet_dashboard/frontend/package.json gsheet_dashboard/frontend/package-lock.json* ./gsheet_dashboard/frontend/

# Install Python and Node dependencies
RUN pip install --no-cache-dir -r gsheet_dashboard/requirements.txt
RUN npm --prefix gsheet_dashboard install
RUN npm --prefix gsheet_dashboard/frontend install

# Copy complete project
COPY . .

# Build React frontend
RUN npm --prefix gsheet_dashboard/frontend run build

# Default port
EXPOSE 8510

# Run server (reads PORT environment variable on Render)
CMD ["python", "gsheet_dashboard/server.py"]
