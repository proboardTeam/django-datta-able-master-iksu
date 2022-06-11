# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.urls import path, re_path
from apps.home import views, opcua_view
from apps.templatetags import repeat
from apps.protocol import opc_ua

from django.contrib import admin
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [

    # The home page
    path('', views.Index.as_view(), name='home'),

    # path('draw/', repeat.JsonGraph.as_view(), name='real'),
    path('draw/', opc_ua.OPCUAgraph.as_view(), name='real'),
    path('other/<str:sensor_id>/<str:sensor_tag>/', repeat.OtherDataGraph.as_view(), name='current'),
    path('opcua/<str:sensor_tag>/', opcua_view.ShowGraph.as_view(), name='opcua'),
    path('speed/<str:sensor_tag>/', opcua_view.protocol_test, name='speed'),
    path('show/<sensor_tag>/draw/', repeat.JsonGraph.as_view(), name='real'),
    path('speed/<str:sensor_tag>/repeater/', repeat.protocol_repeat, name='repeat'),


    path('init/', repeat.init, name='init'),

    # Matches any html file
    re_path(r'^.*\.*', views.pages, name='pages'),

]

