# -*- encoding: utf-8 -*-
"""
Copyright (c) 2019 - present AppSeed.us
"""

# Create your views here.
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from .forms import LoginForm, SignUpForm, DeleteForm
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from rest_framework import status
from .serializer import RequestSerializer
from django.db import DatabaseError
from .models import UserProfile
from apps.factory.models import CompanyProfile


@csrf_exempt
def login_view(request):
    form = LoginForm(request.POST or None)

    # print(request.user)
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data.get("username", "")
        password = form.cleaned_data.get("password", "")
        save_flag = form.cleaned_data.get('save_details', 0)

        print(save_flag)

        try:
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)

                # request.session["test"] = "test literal"
                user_id = RequestSerializer.request_name_check(user)
                request.session["userId"] = user_id
                # if save_flag is True:
                #     request.session["saveFlag"] = save_flag

                # info = UserProfile.objects.filter(username=username)
                # request.session["username"] = info.values_list("username", flat=True)
                # request.session["company"] = info.values_list("company", flat=True)

                # return index(request, info)
                # return render(request, "home/index.html", {"info": info, "msg": msg})
                return redirect("/")

            else:
                msg = "아이디 또는 비밀번호를 잘못 입력하셨습니다."
                return render(request, "accounts/login.html", {"form": form, "msg": msg})

        except DatabaseError:
            msg = "데이터 베이스가 존재하지 않습니다."
            return render(request, "accounts/login.html", {"form": form, "msg": msg})

        except ValueError:
            msg = "아이디 또는 비밀번호를 잘못 입력하셨습니다."
            return render(request, "accounts/login.html", {"form": form, "msg": msg})

    else:
        msg = "환영합니다."
        return render(request, "accounts/login.html", {"form": form, "msg": msg})


@csrf_exempt
def register_user(request):
    msg = None
    success = False

    form = SignUpForm(request.POST or None)
    if request.method == "POST":

        if form.is_valid():
            username = form.cleaned_data.get("username", "")
            email = form.cleaned_data.get("email", "")
            company = form.cleaned_data.get("company", "")
            raw_password = form.cleaned_data.get("password1", "")
            check_password = form.cleaned_data.get("password2", "")
            is_admin = form.cleaned_data.get("is_admin", 0)
            # info = {'username': username, 'email': email, 'company': company, 'password': raw_password}

            if raw_password == check_password:
                try:
                    if not is_admin:
                        user = RequestSerializer.request_create(username=username, email=email, company=company,
                                                                password=raw_password)

                    else:
                        user = RequestSerializer.request_super_create(username=username, email=email, company=company,
                                                                      password=raw_password)
                    # form.user = user
                    # form.company = company
                    # form.save()
                    # authenticate(username=username, email=email, company=company, password=raw_password)
                    authenticate(user)

                    # info = User.objects.filter(username=username)
                    msg = 'User created - please <a href="/login">login</a>.'
                    success = True

                except DatabaseError:
                    msg = "데이터베이스가 존재하지 않습니다."
                    return render(request, "accounts/register.html", {"form": form, "msg": msg})

        else:
            msg = '유효하지 않은 정보입니다.'
            # return JsonResponse(form.data, status=400)
            return render(request, "accounts/register.html", {"form": form, "msg": msg})
    else:
        form = SignUpForm()

    return render(request, "accounts/register.html", {"form": form, "msg": msg, "success": success})


def logout_view(request):

    logout(request)

    for key in list(request.session.keys()):
        del request.session[key]

    login_view(request)

    return redirect("/")


def account_close_view(request):
    form = DeleteForm(request.POST or None)
    # DELETE
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data.get("username", "")
        password = form.cleaned_data.get("password", "")

        try:
            user = authenticate(username=username, password=password)

            if user is not None:
                request.session["test"] = "test literal"
                RequestSerializer.request_delete(user)
                request.session.flush()

                return redirect("/")

            else:
                msg = "아이디 또는 비밀번호를 잘못 입력하셨습니다."
                return render(request, "accounts/login.html", {"form": form, "msg": msg})

        except DatabaseError:
            msg = "데이터 베이스가 존재하지 않습니다."
            return render(request, "accounts/login.html", {"form": form, "msg": msg})

        except ValueError:
            msg = "아이디 또는 비밀번호를 잘못 입력하셨습니다."
            return render(request, "accounts/login.html", {"form": form, "msg": msg})

    else:
        msg = "탈퇴하시려면 로그인과 비밀번호를 입력해주세요."
        return render(request, "accounts/close-account.html", {"form": form, "msg": msg})


