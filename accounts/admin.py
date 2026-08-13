from django.contrib import admin

from .models import Profile, WishlistItem

admin.site.register([Profile, WishlistItem])
