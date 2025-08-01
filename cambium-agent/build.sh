#!/bin/bash

echo "Building Cambium Metrics Collector..."

# Install Playwright dependencies
echo "Installing Playwright dependencies..."
go run github.com/playwright-community/playwright-go/cmd/playwright@latest install

# Install Go dependencies
echo "Installing Go dependencies..."
go mod tidy

# Build the application
echo "Building application..."
go build -o cambium-metrics-collector main.go

echo "Build completed! Run './cambium-metrics-collector' to start the application."
