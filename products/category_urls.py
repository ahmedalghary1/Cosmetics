from django.urls import path

from . import views

app_name = "product_categories"

urlpatterns = [path("<str:category_slug>/", views.product_list, name="detail")]
