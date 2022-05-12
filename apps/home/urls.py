# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.urls import path, re_path
from apps.home import views, opcua_view
from apps.templatetags import repeat
from django.contrib import admin

urlpatterns = [

    # The home page
    path('', views.index, name='home'),
    # path('result/<str:sensor_tag>/', views.result_json, name='result'),
    path('show/<sensor_tag>/', views.ShowGraph.as_view(), name='show'),
    path('other/<str:sensor_tag>/', views.OtherDataGraph.as_view(), name='current'),
    path('opcua/<str:sensor_tag>/', opcua_view.ShowGraph.as_view(), name='opcua'),
    path('speed/<str:sensor_tag>/', opcua_view.protocol_test, name='speed'),
    path('show/<sensor_tag>/draw/', repeat.JsonGraph.as_view(), name='real'),
    path('draw/', repeat.JsonGraph.as_view(), name='real'),
    path('speed/<str:sensor_tag>/repeater/', repeat.protocol_repeat, name='repeat'),


    path('init/', views.init, name='init'),

    # Matches any html file
    re_path(r'^.*\.*', views.pages, name='pages'),

]
