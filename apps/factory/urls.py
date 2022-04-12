# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.urls import path
from .views import details_view
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path('details/', details_view, name="details"),

]
