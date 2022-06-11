# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django.contrib import admin
from django.contrib.auth.models import Group
from .models import UserProfile
from apps.factory.models import CompanyProfile, CompanyType, Factory, Server, Machine, MachineType, Sensor
from django import forms


class UserInline(admin.StackedInline):
    model = UserProfile


class CompanyTypeInline(admin.StackedInline):
    model = CompanyType


class CompanyInline(admin.StackedInline):
    model = CompanyProfile


class FactoryInline(admin.StackedInline):
    model = Factory


class ServerInline(admin.StackedInline):
    model = Server


class MachineInline(admin.StackedInline):
    model = Machine

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'machine_type_fk':
            return MachineTypeChoiceField(queryset=MachineType.objects.all())


class MachineTypeInline(admin.StackedInline):
    model = MachineType


class SensorInline(admin.StackedInline):
    model = Sensor

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'server_fk':
            return ServerChoiceField(queryset=Server.objects.all())
        if db_field.name == 'factory_fk':
            return FactoryChoiceField(queryset=Factory.objects.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class CompanyTypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Company Type: {obj.company_type_name}"


class CompanyChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Company: {obj.company_name}"


class FactoryChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Company: {obj.factory_name}"


class ServerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Server: {obj.server_name}"


class MachineChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Machine: {obj.machine_name}"


class MachineTypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Machine Type: {obj.machine_type_name}"


class SensorChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        print(f'object : {obj}')
        return f"Machine: {obj.sensor_tag}"


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
    readonly_fields = ('password',)
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


@admin.register(CompanyType)
class CompanyTypeAdmin(admin.ModelAdmin):
    # pass
    list_display = ('company_type_name', 'company_name',)
    inlines = (CompanyInline,)

    def company_name(self, obj):
        str_list = []
        result = CompanyProfile.objects.filter(company_type_fk_id=obj.company_type_id).values_list('company_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    company_name.short_description = "company_name"


@admin.register(CompanyProfile)
class CompanyAdmin(admin.ModelAdmin):
    # pass
    list_display = ('company_name', 'company_type_name', 'user_name', 'user_email', 'factory_name',)
    inlines = (UserInline, FactoryInline,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'company_type_fk':
            return CompanyTypeChoiceField(queryset=CompanyType.objects.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

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

    def factory_name(self, obj):
        result = Factory.objects.filter(company_fk_id=obj.company_id).values_list('factory_name', flat=True)

        str_list = []
        for result_val in result:
            str_list.append(result_val)

        return str_list

    factory_name.short_description = "factory_name"

    def company_type_name(self, obj):
        str_list = []
        result = CompanyType.objects.filter(company_type_id=obj.company_type_fk_id).values_list('company_type_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    company_type_name.short_description = "company_type_name"


@admin.register(Factory)
class FactoryAdmin(admin.ModelAdmin):
    # pass
    list_display = ('factory_name', 'company_name',)
    inlines = (ServerInline, MachineInline, SensorInline,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'company_fk':
            return CompanyChoiceField(queryset=CompanyProfile.objects.all())

    def company_name(self, obj):
        str_list = []
        result = CompanyProfile.objects.filter(company_id=obj.company_fk_id).values_list('company_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    company_name.short_description = "company_name"


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    # pass
    list_display = ('server_name', 'factory_name',)
    inlines = (SensorInline,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'factory_fk':
            return FactoryChoiceField(queryset=Factory.objects.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def factory_name(self, obj):
        str_list = []
        result = Factory.objects.filter(factory_id=obj.factory_fk_id).values_list('factory_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    factory_name.short_description = "factory_name"


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    # pass
    list_display = ('machine_name', 'machine_type', 'sensor_name', 'factory_name',)
    inlines = (SensorInline,)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'factory_fk':
            return FactoryChoiceField(queryset=Factory.objects.all())
        if db_field.name == 'machine_type_fk':
            return MachineTypeChoiceField(queryset=MachineType.objects.all())

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # obj = Machine
    def machine_type(self, obj):
        str_list = []
        result = MachineType.objects.filter(machine_type_id=obj.machine_type_fk_id).values_list('machine_type_name',
                                                                                                flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    machine_type.short_description = "machine_type"

    def sensor_name(self, obj):
        str_list = []
        result = Sensor.objects.filter(machine_fk=obj.machine_id).values_list('sensor_tag', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    sensor_name.short_description = "sensor_name"

    def factory_name(self, obj):
        str_list = []
        result = Factory.objects.filter(factory_id=obj.factory_fk_id).values_list('factory_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    factory_name.short_description = "factory_name"


@admin.register(MachineType)
class MachineTypeAdmin(admin.ModelAdmin):
    # pass
    list_display = ('machine_type_name',)


@admin.register(Sensor)
class SensorAdmin(admin.ModelAdmin):
    # pass
    list_display = ('sensor_parent', 'sensor_mac', 'sensor_name', 'machine_name', 'server_name', 'factory_name',)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'server_fk':
            return ServerChoiceField(queryset=Server.objects.all())
        if db_field.name == 'machine_fk':
            return MachineChoiceField(queryset=Machine.objects.all())
        if db_field.name == 'factory_fk':
            return FactoryChoiceField(queryset=Factory.objects.all())

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

    def server_name(self, obj):
        str_list = []
        result = Server.objects.filter(server_id=obj.server_fk_id).values_list('server_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    server_name.short_description = "server_name"

    def factory_name(self, obj):
        str_list = []
        result = Factory.objects.filter(factory_id=obj.factory_fk_id).values_list('factory_name', flat=True)
        for result_val in result:
            str_list.append(result_val)

        return str_list

    factory_name.short_description = "factory_name"


# admin.site.register(UserProfile, UserAdmin)
admin.site.unregister(Group)
