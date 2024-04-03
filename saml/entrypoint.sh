#!/bin/bash

# clear cert sp directory
rm -rf /app/certs/sp/*

# Create certificate and key for saml
openssl req -newkey rsa:2048 -nodes -keyout /app/certs/sp/sp.key -x509 -days 365 -out /app/certs/sp/sp.crt -subj "/C=/ST=/L=/O=InsightFinder/OU=/CN=localhost"

# Run the application
java -jar app.jar --spring.config.location=file:/app/config/application.yml