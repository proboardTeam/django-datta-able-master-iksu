"""
Copyright (c) 2019 - present AppSeed.us
"""
from django.contrib.auth.hashers import make_password
from django.db import models
from django.contrib.auth.models import BaseUserManager, AbstractUser, User
from apps.factory.models import CompanyProfile


# Create your models here.
class UserProfileManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, **extra_fields):
        if 'username' not in extra_fields:
            raise ValueError("이름을 기입해주세요.")

        if 'email' not in extra_fields:
            raise ValueError("이메일을 기입해주세요.")

        if 'company' not in extra_fields:
            raise ValueError("회사명을 기입해주세요.")

        company = CompanyProfile.objects.filter(company_name=extra_fields.get('company'))
        company_id = company.get().company_id
        print(company_id)
        user = self.model(username=extra_fields.get('username'), company_fk_id=company_id,
                          email=self.normalize_email(extra_fields.get('email')), password=extra_fields.get('password'))
        user.password = make_password(extra_fields.get('password'))
        user.save(using=self._db)

        return user

    def create_superuser(self, **extra_fields):
        if 'username' not in extra_fields:
            raise ValueError("이름을 기입해주세요.")

        if 'email' not in extra_fields:
            raise ValueError("이메일을 기입해주세요.")

        if 'company' not in extra_fields:
            raise ValueError("회사명을 기입해주세요.")

        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_admin", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        company = CompanyProfile.objects.filter(company_name=extra_fields.get('company'))
        try:
            company_id = company.get().company_id
        except CompanyProfile.DoesNotExist:
            company_id = None
        print(company_id)
        user = self.model(username=extra_fields.get('username'), company_fk_id=company_id,
                          email=self.normalize_email(extra_fields.get('email')),
                          password=extra_fields.get('password'),
                          is_admin=True, is_staff=True, is_superuser=True)

        user.password = make_password(extra_fields.get('password'))
        user.save(using=self._db)

        return user


class UserProfile(AbstractUser):
    company_fk = models.ForeignKey("factory.CompanyProfile", blank=True, null=True, related_name="companyprofile",
                                   on_delete=models.CASCADE)
    is_admin = models.BooleanField(default=False)

    last_login = None
    first_name = None
    last_name = None
    date_joined = None
    groups = None
    user_permissions = None

    objects = UserProfileManager()

    # @property
    # def company_name(self):
    #     try:
    #         user = UserProfile.objects.filter(username=obj)
    #         result = CompanyProfile.objects.filter(company_id=user.get().company_fk_id)
    #
    #         return result.get().company_name
    #
    #     except CompanyProfile.DoesNotExist:
    #         return u'None'
    #
    # company_name.fget.short_description = '회사명'
