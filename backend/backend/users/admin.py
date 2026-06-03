from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin 
from .models import User


@admin.register(User)
class UserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'department', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Role & Department', {
            'fields': ('role', 'department', 'phone_number')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role & Department', {
            'fields': ('role', 'department', 'phone_number')
        }),
    )