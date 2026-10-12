from services.tool_data import EnterpriseToolDataService


class ServiceSettings:
    database_url = "postgresql+asyncpg://user:password@localhost:5432/test"
    database_schema = ""


def test_allowlisted_product_query_uses_postgresql(monkeypatch):
    service = EnterpriseToolDataService(ServiceSettings())

    async def fetchrow(statement, identifier):
        assert "FROM products" in statement
        assert identifier == "NX-MEET-PRO"
        return {
            "sku": identifier,
            "name": "星云会议终端专业版",
            "list_price": 6999.0,
            "warranty_years": 3,
        }

    monkeypatch.setattr(service, "_fetchrow", fetchrow)
    result = service.query("product", "nx-meet-pro")
    assert result["found"] is True
    assert result["list_price"] == 6999.0


def test_inventory_lookup_uses_postgresql_and_normalizes_identifier(monkeypatch):
    service = EnterpriseToolDataService(ServiceSettings())

    async def fetchrow(statement, identifier):
        assert "FROM product_inventory" in statement
        return {"identifier": identifier, "available": 3, "reserved": 1, "warehouse": "测试仓"}

    monkeypatch.setattr(service, "_fetchrow", fetchrow)
    assert service.lookup("inventory", "sku-1")["available"] == 3


def test_missing_tool_record_is_reported(monkeypatch):
    service = EnterpriseToolDataService(ServiceSettings())

    async def fetchrow(_statement, _identifier):
        return None

    monkeypatch.setattr(service, "_fetchrow", fetchrow)
    assert service.lookup("inventory", "missing")["found"] is False
