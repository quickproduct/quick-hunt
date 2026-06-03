# QuickHunt

QuickHunt is the AI job-hunter service in the [QuickProduct](https://github.com/quickproduct) ecosystem.

## Repository Structure

```
quick-hunt/
├── backend/          # Python services (API, scraper, workers) + tests
│   ├── services/     # api, scraper, and other microservices
│   └── tests/        # unit and integration tests
├── frontend/
│   └── dashboard/    # Next.js dashboard
├── mobile/           # Mobile client
├── mcp/              # MCP server integration
├── infra/            # Dockerfiles and infrastructure config
├── k8s/              # Kubernetes manifests
└── docs/             # Documentation
```

## Getting Started

### Backend (Python)

```bash
pip install -r backend/requirements-shared.txt
pip install -r backend/services/api/requirements.txt
python -m pytest -c backend/pytest.ini backend/tests/unit/
```

Requires **Python 3.11+**, PostgreSQL (pgvector), and Redis.

### Frontend (Next.js)

```bash
cd frontend/dashboard
npm install
npm run dev
```

Requires **Node.js 20+**.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

[MIT](LICENSE) © 2026 QuickProduct Authors

## Links

- [QuickProduct organization](https://github.com/quickproduct)
