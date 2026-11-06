// Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
// For license information, please see license.txt

// The framework's tree method ignores owner isolation; see wallet/treeview.py.
frappe.treeview_settings["Wallet Category"] = {
	get_tree_nodes: "wallet.treeview.get_children",
};
