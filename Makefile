.PHONY: backend-test backend-lint frontend-build security-scan security-tools

security-tools:
	@command -v gitleaks >/dev/null || { echo "gitleaks is required. Install it before running security-scan."; exit 127; }

security-scan: security-tools
	git ls-files --cached --others --exclude-standard -z | xargs -0 -n1 gitleaks dir --no-banner --redact --config .gitleaks.toml

backend-test:
	cd backend && pytest

backend-lint:
	cd backend && ruff check .

frontend-build:
	cd frontend && npm run build
