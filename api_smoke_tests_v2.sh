#!/bin/bash
API_BASE="http://127.0.0.1:8765"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

tests_run=0
tests_passed=0
tests_failed=0

test_endpoint() {
    local name="$1"
    local url="$2"
    local expected_pattern="$3"
    
    tests_run=$((tests_run + 1))
    echo -n "Test $tests_run: $name ... "
    
    response=$(curl -s "$API_BASE$url" 2>&1)
    
    if echo "$response" | grep -qE "$expected_pattern"; then
        echo -e "${GREEN}PASS${NC}"
        tests_passed=$((tests_passed + 1))
        return 0
    else
        echo -e "${RED}FAIL${NC}"
        echo "  Expected pattern: $expected_pattern"
        echo "  Got: $response"
        tests_failed=$((tests_failed + 1))
        return 1
    fi
}

echo "=== API Smoke Tests (v2) ==="
echo ""

test_endpoint "Health Ping" "/health/ping" "pong"
test_endpoint "Root Endpoint" "/" "Platform.*God"
test_endpoint "List Agents" "/api/v1/agents" "agents"
test_endpoint "Get Single Agent" "/api/v1/agents/PG_DISCOVERY" "PG_DISCOVERY"
test_endpoint "List Chains" "/api/v1/chains" "chains"
test_endpoint "Get Single Chain" "/api/v1/chains/full_analysis" "full_analysis"
test_endpoint "List Runs" "/api/v1/runs" "runs"
test_endpoint "Registry Index" "/api/v1/registry/index" "entity_types"
test_endpoint "Metrics Endpoint" "/metrics" "pgod_"

echo ""
echo "=== Results ==="
echo "Tests run: $tests_run"
echo -e "${GREEN}Passed: $tests_passed${NC}"
echo -e "${RED}Failed: $tests_failed${NC}"

if [ $tests_failed -eq 0 ]; then
    echo -e "\n${GREEN}All smoke tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}Some tests failed!${NC}"
    exit 1
fi
