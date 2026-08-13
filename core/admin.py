from django.contrib import admin

from .models import Banner, ContactMessage, ContentPage, RoutineStep, SocialGalleryImage, StoreSettings

admin.site.register([StoreSettings, Banner, ContentPage, ContactMessage, SocialGalleryImage, RoutineStep])
