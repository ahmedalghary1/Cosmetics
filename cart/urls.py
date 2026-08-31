from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.detail, name="detail"),
    path("add/<int:product_id>/", views.add, name="add"),
    path("toggle/<int:product_id>/", views.toggle, name="toggle"),
    path("update/<int:product_id>/", views.update, name="update"),
    path("remove/<int:product_id>/", views.remove, name="remove"),
    path("coupon/", views.apply_coupon, name="coupon"),
]
