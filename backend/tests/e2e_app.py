"""Test-only ASGI entry point: real app/adapters with intercepted upstream HTTP.

Requires an explicitly isolated local database. Not copied into production images.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.integrations.model_gateway import ModelGatewayClient
from app.main import create_app
from tests.upstream_fixture import response

database_url = os.environ.get("TEST_DATABASE_URL", "")
url = make_url(database_url)
if url.host not in {"127.0.0.1", "localhost"} or not url.database.endswith("_test"):
    raise RuntimeError("E2E requires an explicit local PostgreSQL *_test database")

ModelGatewayClient._client = lambda self, timeout=None: httpx.AsyncClient(
    transport=httpx.MockTransport(response), timeout=timeout or 10,
)
app = create_app(Settings(
    _env_file=None, database_url=database_url,
    model_gateway_base_url="https://test-upstream.invalid",
    model_gateway_api_key="test-only-credential",
    storage_path=Path(__file__).resolve().parents[1] / ".pytest_e2e" / "uploads",
    cors_origins="http://127.0.0.1:3100,http://localhost:3100",
    pdf_render_dpi=200,  # Explicit legacy-coordinate profile; pages remain <=2 MP.
))

# Browser regressions explicitly provision current-schema dynamic definitions.
# Production startup deliberately has no built-in PipelineConfig rows.
original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def catalog_lifespan(application):
    from tests.catalog_fixture import register_catalog
    async with original_lifespan(application):
        register_catalog(SimpleNamespace(app=application))
        yield


app.router.lifespan_context = catalog_lifespan
