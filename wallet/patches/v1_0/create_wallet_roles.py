# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

from wallet.install import create_wallet_roles


def execute() -> None:
	"""Create the Wallet User role on sites where the app predates it.

	Runs in `pre_model_sync` because every wallet doctype's permissions link to this
	role, and doctype sync fails on a dangling link.
	"""
	create_wallet_roles()
