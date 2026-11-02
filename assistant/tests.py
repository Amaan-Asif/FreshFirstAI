import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from google.genai import errors
from pydantic import BaseModel

from .client import AIServiceError, generate_json
from .models import AIUsage
from .usage import UsageLimitExceeded, check_and_record

User = get_user_model()

GOOD_TEXT = '{"message": "hello"}'


class Answer(BaseModel):
    message: str


def fake_response(text):
    """What a successful Gemini call returns (we only use its .text)."""
    return SimpleNamespace(text=text)


def make_api_error(code):
    """Build the kind of error the Google library raises."""
    try:
        return errors.APIError(
            code, {"error": {"code": code, "message": "test error", "status": "TEST"}}
        )
    except Exception:
        error = errors.APIError.__new__(errors.APIError)
        Exception.__init__(error, f"{code} test error")
        error.code = code
        return error


@override_settings(GEMINI_API_KEY="test-key", GEMINI_MODELS=["model-a", "model-b"])
class GenerateJsonTests(SimpleTestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)  # keep the test output quiet
        self.addCleanup(logging.disable, logging.NOTSET)

    def run_with(self, results):
        """Call generate_json with a fake Gemini client that returns `results` in order."""
        with patch("assistant.client.genai.Client") as client_class:
            generate = client_class.return_value.models.generate_content
            generate.side_effect = results
            try:
                return generate_json("Say hello", Answer)
            finally:
                self.calls = [call.kwargs["model"] for call in generate.call_args_list]

    def test_valid_answer_is_returned_as_the_schema_object(self):
        result = self.run_with([fake_response(GOOD_TEXT)])
        self.assertIsInstance(result, Answer)
        self.assertEqual(result.message, "hello")
        self.assertEqual(self.calls, ["model-a"])

    def test_busy_model_falls_back_to_the_next_one(self):
        result = self.run_with([make_api_error(503), fake_response(GOOD_TEXT)])
        self.assertEqual(result.message, "hello")
        self.assertEqual(self.calls, ["model-a", "model-b"])

    def test_timeout_falls_back_to_the_next_model(self):
        result = self.run_with([TimeoutError("took too long"), fake_response(GOOD_TEXT)])
        self.assertEqual(result.message, "hello")
        self.assertEqual(self.calls, ["model-a", "model-b"])

    def test_unreadable_answer_falls_back_to_the_next_model(self):
        result = self.run_with([fake_response("this is not json"), fake_response(GOOD_TEXT)])
        self.assertEqual(result.message, "hello")
        self.assertEqual(self.calls, ["model-a", "model-b"])

    def test_empty_answer_falls_back_to_the_next_model(self):
        result = self.run_with([fake_response(""), fake_response(GOOD_TEXT)])
        self.assertEqual(result.message, "hello")
        self.assertEqual(self.calls, ["model-a", "model-b"])

    def test_answer_with_the_wrong_shape_falls_back_to_the_next_model(self):
        result = self.run_with([fake_response('{"wrong": 1}'), fake_response(GOOD_TEXT)])
        self.assertEqual(result.message, "hello")
        self.assertEqual(self.calls, ["model-a", "model-b"])

    def test_quota_used_up_everywhere_gives_a_quota_message(self):
        with self.assertRaises(AIServiceError) as context:
            self.run_with([make_api_error(429), make_api_error(429)])
        self.assertIn("free daily quota", str(context.exception))
        self.assertEqual(self.calls, ["model-a", "model-b"])

    def test_every_model_busy_gives_a_busy_message(self):
        with self.assertRaises(AIServiceError) as context:
            self.run_with([make_api_error(503), make_api_error(504)])
        self.assertIn("busy right now", str(context.exception))

    def test_unknown_model_everywhere_gives_a_configuration_message(self):
        with self.assertRaises(AIServiceError) as context:
            self.run_with([make_api_error(404), make_api_error(404)])
        self.assertIn("configuration problem", str(context.exception))

    def test_bad_key_stops_immediately_without_trying_other_models(self):
        with self.assertRaises(AIServiceError) as context:
            self.run_with([make_api_error(403)])
        self.assertIn("configuration problem", str(context.exception))
        self.assertEqual(self.calls, ["model-a"])

    def test_network_down_everywhere_gives_a_busy_message(self):
        with self.assertRaises(AIServiceError) as context:
            self.run_with([ConnectionError("down"), ConnectionError("down")])
        self.assertIn("busy right now", str(context.exception))
        self.assertEqual(self.calls, ["model-a", "model-b"])

    def test_client_is_built_with_the_key_from_settings(self):
        with patch("assistant.client.genai.Client") as client_class:
            generate = client_class.return_value.models.generate_content
            generate.return_value = fake_response(GOOD_TEXT)
            generate_json("Say hello", Answer)
        self.assertEqual(client_class.call_args.kwargs["api_key"], "test-key")

    def test_prompt_and_json_mode_are_sent_to_gemini(self):
        with patch("assistant.client.genai.Client") as client_class:
            generate = client_class.return_value.models.generate_content
            generate.return_value = fake_response(GOOD_TEXT)
            generate_json("Say hello", Answer)
        kwargs = generate.call_args.kwargs
        self.assertEqual(kwargs["contents"], "Say hello")
        self.assertEqual(kwargs["config"].response_mime_type, "application/json")


class ConfigurationTests(SimpleTestCase):
    @override_settings(GEMINI_API_KEY="", GEMINI_MODELS=["model-a"])
    def test_missing_key_is_reported_and_gemini_is_not_contacted(self):
        with patch("assistant.client.genai.Client") as client_class:
            with self.assertRaises(AIServiceError) as context:
                generate_json("Say hello", Answer)
        self.assertIn("not configured", str(context.exception))
        client_class.assert_not_called()

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODELS=[])
    def test_missing_model_list_is_reported_and_gemini_is_not_contacted(self):
        with patch("assistant.client.genai.Client") as client_class:
            with self.assertRaises(AIServiceError) as context:
                generate_json("Say hello", Answer)
        self.assertIn("not configured", str(context.exception))
        client_class.assert_not_called()


@override_settings(
    AI_DAILY_LIMIT_PER_USER=3, AI_GLOBAL_DAILY_LIMIT=100, AI_COOLDOWN_SECONDS=0
)
class UsageLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user("alice", password="pass12345")
        cls.bob = User.objects.create_user("bob", password="pass12345")

    def use(self, user, times, feature="recipes"):
        for _ in range(times):
            check_and_record(user, feature)

    def test_request_is_recorded(self):
        usage = check_and_record(self.alice, "recipes")
        self.assertEqual(AIUsage.objects.count(), 1)
        self.assertEqual(usage.user, self.alice)
        self.assertEqual(usage.feature, "recipes")

    def test_user_is_blocked_after_the_daily_limit(self):
        self.use(self.alice, 3)
        with self.assertRaises(UsageLimitExceeded) as context:
            check_and_record(self.alice, "recipes")
        self.assertIn("3 AI requests", str(context.exception))
        self.assertEqual(AIUsage.objects.count(), 3)

    def test_limit_applies_per_user(self):
        self.use(self.alice, 3)
        check_and_record(self.bob, "recipes")  # raises an error only if blocked
        self.assertEqual(AIUsage.objects.filter(user=self.bob).count(), 1)

    def test_all_features_share_the_same_daily_limit(self):
        check_and_record(self.alice, "recipes")
        check_and_record(self.alice, "insights")
        check_and_record(self.alice, "recipes")
        with self.assertRaises(UsageLimitExceeded):
            check_and_record(self.alice, "insights")

    @override_settings(AI_GLOBAL_DAILY_LIMIT=2)
    def test_site_wide_limit_blocks_everyone(self):
        self.use(self.alice, 2)
        with self.assertRaises(UsageLimitExceeded) as context:
            check_and_record(self.bob, "recipes")
        self.assertIn("for everyone", str(context.exception))

    @override_settings(AI_COOLDOWN_SECONDS=60)
    def test_quick_second_request_is_blocked_by_the_cooldown(self):
        check_and_record(self.alice, "recipes")
        with self.assertRaises(UsageLimitExceeded) as context:
            check_and_record(self.alice, "recipes")
        self.assertIn("wait a few seconds", str(context.exception))
        self.assertEqual(AIUsage.objects.count(), 1)

    @override_settings(AI_COOLDOWN_SECONDS=60)
    def test_request_after_the_cooldown_is_allowed(self):
        usage = check_and_record(self.alice, "recipes")
        AIUsage.objects.filter(pk=usage.pk).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        check_and_record(self.alice, "recipes")
        self.assertEqual(AIUsage.objects.count(), 2)

    def test_requests_from_earlier_days_do_not_count(self):
        for _ in range(5):
            AIUsage.objects.create(user=self.alice, feature="recipes")
        AIUsage.objects.update(created_at=timezone.now() - timedelta(days=2))
        check_and_record(self.alice, "recipes")  # raises an error only if blocked
        self.assertEqual(AIUsage.objects.count(), 6)