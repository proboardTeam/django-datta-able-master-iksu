# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.urls import path, re_path
from apps.home import views

urlpatterns = [

    # The home page
    path('', views.index, name='home'),
    path('result/<str:sensor_tag>/', views.result_graph, name='graph'),
    path('init/', views.init, name='init'),

    # Matches any html file
    re_path(r'^.*\.*', views.pages, name='pages'),

]
