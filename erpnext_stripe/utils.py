import frappe
import stripe
from frappe.utils import validate_email_address

STRIPE_API_VERSION = "2026-05-27.dahlia"


def configure_stripe(api_key: str):
	stripe.api_key = api_key
	stripe.api_version = STRIPE_API_VERSION


def get_valid_contact_email(email: str | None) -> str | None:
	if not email:
		return None

	email = email.strip()
	if not email:
		return None

	if valid_email := validate_email_address(email, throw=False):
		return valid_email

	normalized_email = _normalize_email_domain(email)
	if normalized_email:
		return validate_email_address(normalized_email, throw=False)

	return None


def log_skipped_contact_email(email: str, stripe_customer_id: str):
	frappe.logger("erpnext_stripe").warning(
		f"Skipping unsupported Stripe customer email {email!r} for {stripe_customer_id}"
	)


def get_stripe_customer_name(stripe_customer, *, fallback_to_identifier: bool = True) -> str | None:
	for candidate in (
		getattr(stripe_customer, "name", None),
		getattr(stripe_customer, "business_name", None),
		getattr(stripe_customer, "individual_name", None),
	):
		if candidate:
			return candidate

	if fallback_to_identifier:
		return _first_non_empty(
			getattr(stripe_customer, "email", None),
			getattr(stripe_customer, "id", None),
		)

	return None


def get_stripe_customer_address(stripe_customer):
	if address := getattr(stripe_customer, "address", None):
		return address

	shipping = getattr(stripe_customer, "shipping", None)
	return getattr(shipping, "address", None) if shipping else None


def get_stripe_customer_contact_name(stripe_customer) -> str | None:
	shipping = getattr(stripe_customer, "shipping", None)
	return _first_non_empty(
		getattr(shipping, "name", None) if shipping else None,
		getattr(stripe_customer, "individual_name", None),
	)


def get_stripe_customer_phone(stripe_customer) -> str | None:
	shipping = getattr(stripe_customer, "shipping", None)
	return _first_non_empty(
		getattr(stripe_customer, "phone", None),
		getattr(shipping, "phone", None) if shipping else None,
	)


def get_stripe_customer_language(stripe_customer) -> str | None:
	for locale in getattr(stripe_customer, "preferred_locales", None) or []:
		for candidate in _language_code_candidates(locale):
			if language := frappe.db.get_value(
				"Language", {"language_code": candidate, "enabled": 1}, "name"
			):
				return language

	return None


def get_country_name_by_code(country_code: str | None) -> str | None:
	if not country_code:
		return None

	return frappe.db.get_value("Country", {"code": country_code.lower()}, "name")


def _first_non_empty(*values: str | None) -> str | None:
	for value in values:
		if value:
			return value

	return None


def _language_code_candidates(locale: str) -> list[str]:
	normalized_locale = locale.replace("_", "-").lower()
	base_locale = normalized_locale.split("-", maxsplit=1)[0]
	return list(dict.fromkeys((normalized_locale, base_locale)))


def _normalize_email_domain(email: str) -> str | None:
	local_part, separator, domain = email.rpartition("@")
	if not separator or not local_part or not domain:
		return None

	try:
		ascii_domain = domain.encode("idna").decode("ascii")
	except UnicodeError:
		return None

	if ascii_domain == domain:
		return None

	return f"{local_part}@{ascii_domain}"
