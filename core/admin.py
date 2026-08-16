from django.contrib import admin

from .models import Banner, ContactMessage, ContentPage, Offer, RoutineStep, SocialGalleryImage, StoreSettings

admin.site.register([StoreSettings, Banner, Offer, ContentPage, ContactMessage, SocialGalleryImage, RoutineStep])
