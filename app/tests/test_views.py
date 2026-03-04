import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from app.models import Recipe


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_recipe_list(api_client):
    url = reverse("recipe-list")
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.data, list)


@pytest.mark.django_db
def test_create_recipe(api_client):
    """POST /api/recipes/ should create a new recipe and return 201."""
    url = reverse("recipe-list")
    payload = {
        "title": "Pasta Carbonara",
        "description": "Classic Italian pasta dish.",
        "time_minutes": 30,
        "price": "12.50",
    }
    response = api_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["title"] == payload["title"]
    assert Recipe.objects.filter(title="Pasta Carbonara").exists()


@pytest.mark.django_db
def test_retrieve_recipe(api_client):
    """GET /api/recipes/<id>/ should return the correct recipe details."""
    recipe = Recipe.objects.create(
        title="Tomato Soup",
        description="Simple tomato soup.",
        time_minutes=20,
        price="5.00",
    )
    url = reverse("recipe-detail", args=[recipe.id])
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["title"] == "Tomato Soup"
    assert response.data["time_minutes"] == 20