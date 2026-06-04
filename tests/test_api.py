import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import io

from app.main import app
from app.models.database import init_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_upload_csv(client):
    csv_content = b"product,revenue,month\nWidget A,1200,January\nWidget B,850,January\nWidget A,1400,February"
    response = await client.post(
        "/api/v1/datasets/upload",
        files={"file": ("test_data.csv", io.BytesIO(csv_content), "text/csv")},
        data={"description": "Test dataset"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == 3
    assert data["dataset_id"] > 0


@pytest.mark.asyncio
async def test_list_datasets(client):
    response = await client.get("/api/v1/datasets")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_upload_non_csv_rejected(client):
    response = await client.post(
        "/api/v1/datasets/upload",
        files={"file": ("data.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
    )
    assert response.status_code == 400