#!/bin/bash

# Create certificate and key for saml
openssl req -newkey rsa:2048 -nodes -keyout sp.key -x509 -days 365 -out sp.crt -subj "/C=/ST=/L=/O=InsightFinder/OU=/CN=localhost"

# Move cert and key to correct location
mv sp.crt sp.key /app/certs/sp/

# Run the application
java -jar app.jar --spring.config.location=file:/app/config/application.yml