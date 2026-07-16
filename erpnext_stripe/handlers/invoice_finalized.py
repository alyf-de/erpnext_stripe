from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from stripe import Event


from erpnext_stripe.operations.create_invoice import run as create_invoice


def handle(event: "Event"):
	"""
	Creates a Sales Invoice from a Stripe Invoice. Submit. Attach PDF.
	"""
	create_invoice(event.data.object)
