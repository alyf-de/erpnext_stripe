from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from stripe import Event


from erpnext_stripe.operations.create_lead import run as create_lead


def handle(event: "Event", ignore_permissions: bool = False):
	create_lead(event.data.object, ignore_permissions=ignore_permissions)
