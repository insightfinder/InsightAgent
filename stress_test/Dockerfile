FROM python:3.8.18

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the current directory contents into the container at /usr/src/app
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Run the python script and keep the container alive
CMD ["bash", "-c", "python ./memory-leak-3.py && tail -f /dev/null"]