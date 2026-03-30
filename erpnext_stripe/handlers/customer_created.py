from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from stripe import Event


from erpnext_stripe.operations.create_customer import run as create_customer


def handle(event: "Event", ignore_permissions: bool = False):
	create_customer(event.data.object, ignore_permissions=ignore_permissions)
