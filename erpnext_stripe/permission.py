"""Apps screen visibility for ERPNext Stripe."""

import frappe

ERPNEXT_STRIPE_MODULE = "ERPNext Stripe"


def has_app_permission() -> bool:
	"""Return whether the session user may open ERPNext Stripe on the apps screen."""
	if frappe.session.user == "Guest":
		return False

	user = frappe.get_user()
	if not user.allow_modules:
		user.build_permissions()

	return ERPNEXT_STRIPE_MODULE in user.allow_modules
