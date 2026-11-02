from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

STRONG_PASSWORD = "Str0ng!Passw0rd"


def registration_data(**overrides):
    data = {
        "username": "newuser",
        "email": "new@example.com",
        "password1": STRONG_PASSWORD,
        "password2": STRONG_PASSWORD,
    }
    data.update(overrides)
    return data


class RegisterTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:register")

    def test_register_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your account")

    def test_valid_registration_creates_user_and_logs_in(self):
        response = self.client.post(self.url, registration_data())
        self.assertRedirects(response, reverse("core:home"))
        user = User.objects.get(username="newuser")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_email_is_saved_in_lowercase(self):
        self.client.post(self.url, registration_data(email="New@Example.COM"))
        self.assertEqual(User.objects.get(username="newuser").email, "new@example.com")

    def test_duplicate_email_is_rejected_even_with_different_capitals(self):
        User.objects.create_user("taken", email="taken@example.com", password=STRONG_PASSWORD)
        response = self.client.post(
            self.url, registration_data(email="TAKEN@example.com")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An account with this email already exists.")
        self.assertEqual(User.objects.count(), 1)

    def test_missing_email_is_rejected(self):
        response = self.client.post(self.url, registration_data(email=""))
        self.assertIn("email", response.context["form"].errors)
        self.assertFalse(User.objects.exists())

    def test_mismatched_passwords_are_rejected(self):
        response = self.client.post(
            self.url, registration_data(password2="Different!Passw0rd")
        )
        self.assertIn("password2", response.context["form"].errors)
        self.assertFalse(User.objects.exists())

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            self.url, registration_data(password1="12345678", password2="12345678")
        )
        self.assertIn("password2", response.context["form"].errors)
        self.assertFalse(User.objects.exists())

    def test_logged_in_user_is_redirected_away_from_register(self):
        user = User.objects.create_user("alice", password=STRONG_PASSWORD)
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("core:home"))


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            "alice", email="alice@example.com", password=STRONG_PASSWORD
        )

    def setUp(self):
        self.url = reverse("accounts:login")

    def test_login_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")

    def test_login_with_correct_details(self):
        response = self.client.post(
            self.url, {"username": "alice", "password": STRONG_PASSWORD}
        )
        self.assertRedirects(response, reverse("core:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_with_wrong_password_shows_error(self):
        response = self.client.post(
            self.url, {"username": "alice", "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logged_in_user_is_redirected_away_from_login(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("core:home"))


class LogoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("alice", password=STRONG_PASSWORD)

    def test_logout_signs_the_user_out(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_by_get_request_is_not_allowed(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)