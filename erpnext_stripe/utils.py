import frappe
from frappe.utils import validate_email_address


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
