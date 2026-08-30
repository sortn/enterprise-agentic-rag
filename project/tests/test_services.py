import json

from services.business_api import MockBusinessService
from services.structured_data import StructuredDataService


class ServiceSettings:
    def __init__(self, tmp_path):
        self.structured_db_path = tmp_path / "enterprise.db"
        self.business_data_path = tmp_path / "business.json"


def test_parameterized_product_query(tmp_path):
    service = StructuredDataService(ServiceSettings(tmp_path))
    result = service.query("product", "nx-meet-pro")
    assert result["found"] is True
    assert result["list_price"] == 6999.0


def test_mock_business_api(tmp_path):
    settings = ServiceSettings(tmp_path)
    settings.business_data_path.write_text(
        json.dumps({"inventory": {"SKU-1": {"available": 3}}}), encoding="utf-8"
    )
    service = MockBusinessService(settings)
    assert service.lookup("inventory", "sku-1")["available"] == 3
    assert service.lookup("inventory", "missing")["found"] is False


def test_mock_business_api_bootstraps_demo_data(tmp_path):
    settings = ServiceSettings(tmp_path)
    service = MockBusinessService(settings)

    assert settings.business_data_path.exists()
    assert service.lookup("inventory", "nx-meet-pro")["found"] is True
