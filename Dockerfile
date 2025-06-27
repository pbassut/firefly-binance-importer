FROM python:3.9-slim-buster

# Install pipenv
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install pipenv

# Set work directory
WORKDIR /opt/crypto-trades-firefly-iii

# Copy Pipfile and Pipfile.lock first to leverage Docker cache
COPY Pipfile Pipfile.lock ./

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pipenv install --deploy --system --ignore-pipfile

# Copy the rest of the application code
COPY ./ ./

CMD ["python", "src/main.py"]
