from django.test import TestCase
from users.models import User


class UserPermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin1",
            password="TestPass123!",
            role="admin",
        )
        self.security = User.objects.create_user(
            username="sec1",
            password="TestPass123!",
            role="security_specialist",
        )
        self.ai = User.objects.create_user(
            username="ai1",
            password="TestPass123!",
            role="ai_engineer",
        )
        self.external = User.objects.create_user(
            username="ext1",
            password="TestPass123!",
            role="external_user",
        )

    def test_admin_permissions(self):
        self.assertTrue(self.admin.is_admin)
        self.assertTrue(self.admin.can_manage_accounts)
        self.assertTrue(self.admin.can_configure_system)
        self.assertFalse(self.admin.can_manage_ai_models)
        self.assertFalse(self.admin.can_view_alerts)

    def test_security_specialist_permissions(self):
        self.assertFalse(self.security.is_admin)
        self.assertFalse(self.security.can_manage_accounts)
        self.assertFalse(self.security.can_configure_system)
        self.assertFalse(self.security.can_manage_ai_models)
        self.assertTrue(self.security.can_view_alerts)
        self.assertTrue(self.security.can_chat_with_llm)
        self.assertTrue(self.security.can_generate_reports)

    def test_ai_engineer_permissions(self):
        self.assertFalse(self.ai.is_admin)
        self.assertFalse(self.ai.can_manage_accounts)
        self.assertFalse(self.ai.can_configure_system)
        self.assertTrue(self.ai.can_manage_ai_models)
        self.assertFalse(self.ai.can_view_alerts)
        self.assertFalse(self.ai.can_chat_with_llm)
        self.assertFalse(self.ai.can_generate_reports)

    def test_external_user_permissions(self):
        self.assertFalse(self.external.is_admin)
        self.assertFalse(self.external.can_manage_accounts)
        self.assertFalse(self.external.can_configure_system)
        self.assertFalse(self.external.can_manage_ai_models)
        self.assertFalse(self.external.can_view_alerts)
        self.assertFalse(self.external.can_chat_with_llm)
        self.assertFalse(self.external.can_generate_reports)

    def test_is_external_user_property(self):
        self.assertTrue(self.admin.is_external_user)
        self.assertTrue(self.security.is_external_user)
        self.assertTrue(self.ai.is_external_user)
        self.assertTrue(self.external.is_external_user)

    def test_string_representation(self):
        self.assertIn("admin1", str(self.admin))
        self.assertIn("sec1", str(self.security))