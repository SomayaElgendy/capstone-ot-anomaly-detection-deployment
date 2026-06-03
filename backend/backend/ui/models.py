from django.db import models


class ServiceRequest(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    organization = models.CharField(max_length=150, blank=True, null=True)
    message = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("reviewed", "Reviewed"),
            ("resolved", "Resolved"),
        ],
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.email}"