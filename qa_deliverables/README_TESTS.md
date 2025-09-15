# Test Suite Documentation

## Overview

This test suite validates the functionality and behavior of a FastAPI-based User Management API. The suite runs in two modes:

1. Normal Mode (default)
2. Seed Data Mode (with pre-populated test data)

## Quick Start

```bash
# Install dependencies
pip install -r requirements_test.txt

# Run tests (normal mode)
pytest -v

# Run tests with seed data
TESTS_USE_SEED_DATA=1 pytest -v
```

## Test Suite Structure

### Core Test Modules
- `test_auth.py`: Authentication and authorization
- `test_input_validation.py`: Input validation and constraints
- `test_pagination_sort.py`: List operations and sorting
- `test_rate_limit_and_bulk.py`: Rate limiting and bulk operations
- `test_search.py`: Search functionality
- `test_stats_health.py`: System statistics and health
- `test_users_crud.py`: Basic CRUD operations
- `test_with_seed_data.py`: Seed data compatibility

### Supporting Files
- `conftest.py`: Shared fixtures and utilities
- `requirements_test.txt`: Test dependencies
- `pytest.ini`: Test configuration

## Test Categories

### Functional Tests
- User management operations
- Authentication flows
- Search and filtering
- Pagination and sorting

### Security Tests
- Input validation
- Authorization checks
- Rate limiting
- Data privacy

### Integration Tests
- Database operations
- Bulk processing
- Error handling
- State management

## Test Modes

### Normal Mode
- Clean state for each test
- Isolated test environment
- Full control over test data

### Seed Data Mode
- Pre-populated test data
- Real-world scenarios
- Data consistency checks

## Writing Tests

### Key Fixtures
- `client`: Test client instance
- `unique`: Username generator
- `created_user`: Test user creation

### Conventions
- Use `unique()` for usernames
- Include detailed docstrings
- Mark expected failures with `xfail`

## Running Tests

### Basic Usage
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_auth.py

# Run with specific marker
pytest -m "auth"
```

### Advanced Options
```bash
# Verbose output
pytest -v

# Show coverage
pytest --cov=main

# Generate report
pytest --html=report.html
```

## Test Design Notes

### Intentional Failures
Some tests use `xfail(strict=True)` to document:
- Security requirements
- Authorization rules
- Data leak prevention

### Test Independence
- Tests should be isolated
- Use unique test data
- Clean up after execution

## Contributing

### Adding Tests
1. Follow existing patterns
2. Use provided fixtures
3. Document expectations
4. Include error cases

### Test Requirements
- Clear purpose
- Meaningful assertions
- Proper cleanup
- Comprehensive coverage
