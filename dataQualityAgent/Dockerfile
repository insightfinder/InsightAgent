# Use a lightweight Python base image
FROM python:3.12-slim

# Install Poetry globally
RUN pip install --no-cache-dir poetry

# Set the working directory in the container
WORKDIR /app

# Copy the Poetry files first to leverage Docker caching
COPY . .

# Install dependencies (without dev dependencies in production)
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

# Set the default command to run your application
CMD [ "sleep", "10000"]
