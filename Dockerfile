# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install git (needed for discord.py-self from GitHub)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Re-install the latest discord.py-self from GitHub just in case
RUN pip install -U git+https://github.com/dolfies/discord.py-self@master

# Copy the rest of the application code into the container
COPY . .

# Set environment variables (can be overridden by Koyeb dashboard)
# We won't include DISCORD_TOKEN here for security

# Run the application with -u for unbuffered logs (crucial for Koyeb/Docker)
CMD ["python", "-u", "main.py"]
