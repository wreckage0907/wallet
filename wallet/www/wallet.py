import frappe
from frappe.utils import get_system_timezone

no_cache = 1


def get_context():
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("Please log in to use Wallet."), frappe.PermissionError)

	context = frappe._dict()
	context.boot = get_boot()
	context.boot.csrf_token = frappe.sessions.get_csrf_token()
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev() -> dict:
	"""Boot payload for `yarn dev`, where the page is served by Vite and never passes
	through this template."""
	if not frappe.conf.developer_mode:
		frappe.throw(frappe._("This method is only meant for developer mode"))
	return get_boot()


def get_boot() -> frappe._dict:
	user = frappe.session.user

	return frappe._dict(
		{
			"frappe_version": frappe.__version__,
			"site_name": frappe.local.site,
			"read_only_mode": frappe.flags.read_only,
			"system_timezone": get_system_timezone(),
			"user": user,
			"user_full_name": frappe.utils.get_fullname(user),
		}
	)
