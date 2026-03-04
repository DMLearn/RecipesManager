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


@pytest.mark.django_db
def test_update_recipe(api_client):
    """PUT /api/recipes/<id>/ should update an existing recipe and return 200."""
    recipe = Recipe.objects.create(
        title="Old Title",
        description="Old description.",
        time_minutes=15,
        price="3.00",
    )
    url = reverse("recipe-detail", args=[recipe.id])
    payload = {
        "title": "New Title",
        "description": "Updated description.",
        "time_minutes": 25,
        "price": "7.00",
    }
    response = api_client.put(url, payload, format="json")
    assert response.status_code == status.HTTP_200_OK
    recipe.refresh_from_db()
    assert recipe.title == "New Title"
    assert recipe.time_minutes == 25


@pytest.mark.django_db
def test_delete_recipe(api_client):
    """DELETE /api/recipes/<id>/ should remove the recipe and return 204."""
    recipe = Recipe.objects.create(
        title="To Be Deleted",
        description="This will be deleted.",
        time_minutes=10,
        price="2.00",
    )
    url = reverse("recipe-detail", args=[recipe.id])
    response = api_client.delete(url)
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Recipe.objects.filter(id=recipe.id).exists()