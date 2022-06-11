# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile


class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "이름",
                "class": "form-control"
            }
        ),
    )

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "비밀번호",
                "class": "form-control"
            }
        ))
    save_details = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={
                "class": "checkbox-inline"
            }
        )
    )

    class Meta:
        model = UserProfile
        fields = ('username', 'password', 'save_details')


class SignUpForm(UserCreationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "이름",
                "class": "form-control"
            }
        )
    )

    company = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "회사명",
                "class": "form-control"
            }
        )
    )

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "placeholder": "이메일",
                "class": "form-control"
            }
        )
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "비밀번호",
                "class": "form-control"
            }
        )
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "비밀번호 확인",
                "class": "form-control"
            }
        )
    )

    is_admin = forms.BooleanField(
        widget=forms.CheckboxInput(
            attrs={
                "class": "checkbox-inline"
            }
        )
    )

    class Meta(UserCreationForm.Meta):
        model = UserProfile
        fields = ('username', 'email', 'password1', 'password2', 'is_admin')


class UpdateForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "이름",
                "class": "form-control"
            }
        ),
    )

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "현재 비밀번호",
                "class": "form-control"
            }
        ),
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "새 비밀번호",
                "class": "form-control"
            }
        )
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "새 비밀번호 확인",
                "class": "form-control"
            }
        )
    )

    class Meta:
        model = UserProfile
        fields = ('username', 'password', 'password1', 'password2')


class DeleteForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "placeholder": "이름",
                "class": "form-control"
            }
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "비밀번호",
                "class": "form-control"
            }
        ),
    )

    class Meta:
        model = UserProfile
        fields = ('username', 'password')
