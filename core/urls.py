# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.contrib import admin
from django.urls import path, include, re_path  # add this
from django.conf.urls.static import static
from django.conf import settings
from django.views.static import serve

# admin.site.index_template = 'admin/custom.html'
# admin.autodiscover()

urlpatterns = [
    path('admin/', admin.site.urls),          # Django admin route
    path("", include("apps.authentication.urls")),  # Auth routes - login / register
    path("", include("apps.home.urls")),           # UI Kits Html files
    path("", include("apps.factory.urls")),
]

