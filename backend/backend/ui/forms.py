from django import forms
from .models import ServiceRequest


class ServiceRequestForm(forms.ModelForm):
    class Meta:
        model = ServiceRequest
        fields = ["name", "email", "organization", "message"]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "required": True}),
            "email": forms.EmailInput(attrs={"class": "form-control", "required": True}),
            "organization": forms.TextInput(attrs={"class": "form-control"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "required": True}),
        }