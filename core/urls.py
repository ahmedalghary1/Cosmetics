from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("contact/", views.contact, name="contact"),
    path("pages/<str:slug>/", views.content_page, name="page"),
]
