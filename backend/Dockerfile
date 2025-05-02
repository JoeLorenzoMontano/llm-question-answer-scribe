FROM python:3.10

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Make wait script executable
RUN chmod +x wait-for-it.sh

# Create a startup script that doesn't wait for dependencies
# We'll handle connection retries in the application code instead
RUN echo '#!/bin/bash\n\
# Start the application directly - resilience is built into the code\n\
uvicorn main:app --host 0.0.0.0 --port 8000 --reload' > start.sh && \
chmod +x start.sh

CMD ["./start.sh"]
