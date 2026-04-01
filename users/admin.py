from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Share Bear Profile', {'fields': ('graduation_year',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Share Bear Profile', {'fields': ('graduation_year',)}),
    )
