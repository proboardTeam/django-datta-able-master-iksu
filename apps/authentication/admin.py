# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.contrib import admin
from django.contrib.auth.models import Group
from .models import UserProfile
from apps.factory.models import CompanyProfile, Machine, Sensor
from .serializer import RequestSerializer, RequestFactorySerializer
from django import forms


# class RequestSerializer(serializers.ModelSerializer):
#
#     class Meta:
#         model = CompanyProfile
#         fields = ('company_id', 'company_name')
#
#     @staticmethod
#     def request_check(request):
#         info = CompanyProfile.objects.get(company_name=request)
#         return info.id
#
#     @staticmethod
#     def request_my_info(request):
#         RequestSerializer.request_check(request)
#
#     @staticmethod
#     def request_create(**request):
#         response = CompanyProfile.save(**request)
#         return response
#
#     @staticmethod
#     def request_delete(request):
#         info = CompanyProfile.objects.get(company_name=request)
#         info.delete()


class CompanyInline(admin.StackedInline):
    model = CompanyProfile


class UserInline(admin.StackedInline):
    model = UserProfile


class MachineInline(admin.StackedInline):
    model = Machine


class SensorInline(admin.StackedInline):
    model = Sensor


class CompanyChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Company: {obj.company_name}"


class MachineChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Machine: {obj.machine_name}"

# Register your models here.
# 맨 처음 화면, 등록된 모델마다 메뉴가 생김
@admin.register(UserProfile)
class UserAdmin(admin.ModelAdmin):
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'company_fk':
            return CompanyChoiceField(queryset=CompanyProfile.objects.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # Users를 클릭하면 보이는 초기 화면
    # form = UserCreationForm
    list_display = ('username', 'email', 'company_name_list', 'is_admin')
    list_filter = ('is_admin',)
    readonly_fields = ('password', )
    # inlines = (CompanyInline,)

    # User 목록 중 하나를 클릭하면 상세 정보 표시
    fieldsets = [
        ('Admin Login', {'fields': ('username', 'password')}),
        ('Personal information', {'fields': ['email', 'company_fk']}),
        ('Permissions', {'fields': ('is_admin',)}),
    ]

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'company_fk', 'password1', 'password2')}
         ),
    )
    search_fields = ('username',)
    ordering = ('username',)
    filter_horizontal = ()

    # obj = username
    # def company_name(self, obj):
    #     user = UserProfile.objects.filter(username=obj)
    #     result = CompanyProfile.objects.filter(company_id=user.get().company_fk_id)
    #
    #     return result.get().company_name
    #
    # company_name.short_description = "company_name"

    def company_name_list(self, obj):
        user = UserProfile.objects.filter(username=obj)
        result = CompanyProfile.objects.filter(company_id=user.get().company_fk_id)

        if not result:
            result = 0
            return result

        return obj.company_fk.company_name

    company_name_list.short_description = "company_name_list"
    company_name_list.admin_order_field = "company_name_list"


@admin.register(CompanyProfile)
class CompanyAdmin(admin.ModelAdmin):
    # pass
    list_display = ('company_name', 'user_name', 'user_email')
    inlines = (UserInline, MachineInline,)

    # obj = CompanyProfile
    def user_name(self, obj):
        result = UserProfile.objects.filter(company_fk_id=obj.company_id).values_list('username', flat=True)

        str_list = []
        for result_val in result:
            str_list.append(result_val)

        return str_list

    user_name.short_description = "user_name"

    def user_email(self, obj):
        result = UserProfile.objects.filter(company_fk_id=obj.company_id).values_list('email', flat=True)

        str_list = []
        for result_val in result:
            str_list.append(result_val)

        return str_list

    user_email.short_description = "user_email"

    # @staticmethod
    # def machine_name(obj):
    #     result = Machine.objects.filter(machine=obj)
    #     if not result:
    #         return 'None'
    #     return result['machine_name']
    #
    # machine_name.short_description = "machine_name"
    #
    # @staticmethod
    # def sensor_name(obj):
    #     result = Sensor.objects.filter(sensor=obj)
    #     if not result:
    #         return 'None'
    #     return result['sensor_tag']
    #
    # user_email.short_description = "sensor_name"


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    # pass
    list_display = ('machine_name', 'sensor_name',)
    inlines = (SensorInline,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'company_fk':
            return CompanyChoiceField(queryset=CompanyProfile.objects.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # obj = Machine
    def sensor_name(self, obj):
        str_list = []
        result = Sensor.objects.filter(machine_fk=obj.machine_id).values_list('sensor_tag', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    sensor_name.short_description = "sensor_name"


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    # pass
    list_display = ('sensor_parent', 'sensor_mac', 'sensor_name', 'machine_name', 'company_name', )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'machine_fk':
            return MachineChoiceField(queryset=Machine.objects.all())
        if db_field.name == 'company_fk':
            return CompanyChoiceField(queryset=CompanyProfile.objects.all())

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # obj = Sensor
    def sensor_name(self, obj):
        return obj.sensor_tag

    sensor_name.short_description = "sensor_name"

    def machine_name(self, obj):
        str_list = []
        result = Machine.objects.filter(machine_id=obj.machine_fk_id).values_list('machine_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    machine_name.short_description = "machine_name"

    def company_name(self, obj):
        str_list = []
        result = CompanyProfile.objects.filter(company_id=obj.company_fk_id).values_list('company_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    company_name.short_description = "company_name"

# admin.site.register(UserProfile, UserAdmin)
admin.site.unregister(Group)
