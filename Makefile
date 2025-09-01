"""
Code formatting and linting configuration for Carlos AI Assistant
Enforces consistent code style and quality standards
"""

# Makefile for development tasks

.PHONY: help install test lint format type-check clean all

help:
	@echo "Available commands:"
	@echo "  install     Install development dependencies"
	@echo "  test        Run test suite"
	@echo "  lint        Run linting checks"
	@echo "  format      Format code with black and isort"
	@echo "  type-check  Run mypy type checking"
	@echo "  clean       Clean up temporary files"
	@echo "  all         Run full quality check pipeline"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v --cov=carlos --cov-report=html --cov-report=term

lint:
	flake8 carlos_enhanced.py app_enhanced.py tests/
	black --check carlos_enhanced.py app_enhanced.py tests/
	isort --check-only carlos_enhanced.py app_enhanced.py tests/

format:
	black carlos_enhanced.py app_enhanced.py tests/
	isort carlos_enhanced.py app_enhanced.py tests/

type-check:
	mypy carlos_enhanced.py app_enhanced.py

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .coverage htmlcov/ .pytest_cache/ .mypy_cache/
	rm -rf build/ dist/ *.egg-info/

all: format lint type-check test
	@echo "✅ All quality checks passed!"