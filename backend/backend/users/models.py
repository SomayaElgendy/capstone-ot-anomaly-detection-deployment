from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('security_specialist', 'Security Specialist'),
        ('ai_engineer', 'AI Engineer'),
        ('external_user', 'External User'),
    ]
    
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
    )
    
    department = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_admin(self):
        """Full system access"""
        return self.role == 'admin' or self.is_superuser

    @property
    def can_manage_accounts(self):
        """FR2, FR3: Account granting and management"""
        return self.is_admin

    @property
    def can_configure_system(self):
        """FR4: System configuration"""
        return self.is_admin

    @property
    def can_manage_ai_models(self):
        """FR5, FR6: Models and LLM database management"""
        return self.role == 'ai_engineer'

    @property
    def can_view_alerts(self):
        """FR9-FR13: Monitor attacks, view alerts/timeline/responses"""
        return self.role == 'security_specialist'

    @property
    def can_chat_with_llm(self):
        """FR14: LLM chat assistant"""
        return self.role == 'security_specialist'

    @property
    def can_generate_reports(self):
        """FR15: Report generation"""
        return self.role == 'security_specialist'

    @property
    def is_external_user(self):
        """FR7, FR8: External website access only"""
        return self.role in ['security_specialist', 'external_user', 'ai_engineer', 'admin']
        
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class PasswordResetRequest(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Resolved", "Resolved"), 
        ]

    username_or_email = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    matched_user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="password_reset_requests",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Password reset request: {self.username_or_email} ({self.status})"