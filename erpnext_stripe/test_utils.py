import unittest
from types import SimpleNamespace
from unittest.mock import patch

from erpnext_stripe.utils import STRIPE_API_VERSION, configure_stripe


class TestStripeUtils(unittest.TestCase):
	def test_configure_stripe_sets_api_key_and_version(self):
		stripe = SimpleNamespace(api_key=None, api_version=None)

		with patch("erpnext_stripe.utils.stripe", stripe):
			configure_stripe("rk_test")

		self.assertEqual(stripe.api_key, "rk_test")
		self.assertEqual(stripe.api_version, STRIPE_API_VERSION)
