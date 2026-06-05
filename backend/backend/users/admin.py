from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin 
from .models import User, PasswordResetRequest


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

@admin.register(PasswordResetRequest)
class PasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ("username_or_email", "matched_user", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("username_or_email", "message", "matched_user__username")
    readonly_fields = ("username_or_email", "message", "matched_user", "created_at")