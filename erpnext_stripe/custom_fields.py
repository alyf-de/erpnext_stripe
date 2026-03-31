def _(x):
	"""Dummy function to mark strings as translatable"""
	return x


def get_custom_fields():
	stripe_id_field = {
		"fieldname": "stripe_id",
		"fieldtype": "Data",
		"label": _("Stripe ID"),
		"read_only": 1,
		"translatable": 0,
		"no_copy": 1,
		"unique": 1,
	}

	return {
		"Customer": [
			{
				"insert_after": "customer_details",
				**stripe_id_field,
			},
		],
		"Item": [
			{
				"insert_after": "brand",
				**stripe_id_field,
			},
		],
		"Sales Invoice": [
			{
				"insert_after": "status",
				**stripe_id_field,
			},
		],
		"Lead": [
			{
				"insert_after": "lead_name",
				**stripe_id_field,
			},
		],
	}
