from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("", views.product_list, name="list"),
    path("back-in-stock/<int:product_id>/", views.subscribe_back_in_stock, name="back_in_stock"),
    path("<str:slug>/", views.product_detail, name="detail"),
]
