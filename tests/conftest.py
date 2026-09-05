import pytest

from app import create_app


@pytest.fixture()
def app():
    return create_app(testing=True)


@pytest.fixture()
def app_client():
    app = create_app(testing=True)
    with app.test_client() as client:
        yield client
