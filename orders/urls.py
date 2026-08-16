from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.checkout, name="checkout"),
    path("shipping-quote/", views.shipping_quote, name="shipping_quote"),
    path("success/<str:order_number>/", views.success, name="success"),
    path("order/<str:order_number>/", views.order_detail, name="detail"),
    path("order/<str:order_number>/return/", views.request_return, name="request_return"),
]
