#!/bin/bash

# Test script for the receiver agent

BASE_URL="http://ec2-34-236-220-137.compute-1.amazonaws.com:8080"

echo "=== InsightFinder Receiver Agent - Test Suite ==="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Function to print test result
print_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASSED${NC}: $2"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC}: $2"
        ((FAILED++))
    fi
    echo ""
}

# Test 1: Health Check
echo "Test 1: Health Check Endpoint"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$RESPONSE" -eq 200 ]; then
    print_result 0 "Health check returned 200"
else
    print_result 1 "Health check failed with status $RESPONSE"
fi

# Test 2: Valid ServiceNow Request
echo "Test 2: Valid ServiceNow Request"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/data" \
  -H "Content-Type: application/json" \
  -d '{
    "environment": "staging",
    "timestamp": 1763660093000,
    "agentType": 0,
    "metriclist": [
      {"name": "service_now_creation_time", "value": 150.5},
      {"name": "service_now_feedback_time", "value": 200.3}
    ]
  }' \
  -w "\n%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" -eq 200 ]; then
    if echo "$BODY" | grep -q '"success":true'; then
        print_result 0 "Valid ServiceNow request processed successfully"
    else
        print_result 1 "Response indicates failure: $BODY"
    fi
else
    print_result 1 "Request failed with status $HTTP_CODE"
fi

# Summary
echo "======================================"
echo -e "Test Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo "======================================"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
