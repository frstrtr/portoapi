from fastapi.testclient import TestClient
from api.v1.main import app

client = TestClient(app)

def test_list_invoices():
    response = client.get("/v1/invoices")
    assert response.status_code == 200
    assert "invoices" in response.json()

def test_setup_webhook():
    response = client.post("/v1/webhooks")
    assert response.status_code == 200
    assert response.json()["status"] == "webhook set"
