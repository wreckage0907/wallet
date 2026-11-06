# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

from wallet.setup.custom_fields import create_wallet_custom_fields


def execute() -> None:
	"""Add the per-user MCP write opt-in to User. Off for everyone: a user who had MCP writes
	through the site-wide flag alone now has to opt in, which is the point."""
	create_wallet_custom_fields()
