// Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
// For license information, please see license.txt

frappe.ui.form.on("Wallet Statement Import", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (
			frm.doc.statement_file &&
			["Draft", "Failed", "Preview Ready"].includes(frm.doc.status)
		) {
			frm.add_custom_button(__("Parse Statement"), () => parse_statement(frm)).addClass(
				"btn-primary"
			);
		}

		if (frm.doc.status === "Preview Ready" && frm.doc.new_rows > 0) {
			frm.add_custom_button(__("Import {0} Rows", [frm.doc.new_rows]), () =>
				commit_import(frm)
			).addClass("btn-primary");
		}

		if (frm.doc.status === "Preview Ready" && frm.doc.detected_mapping) {
			frm.add_custom_button(__("Save as Format"), () => save_as_format(frm));
		}

		show_variance(frm);
	},
});

function parse_statement(frm) {
	frappe.call({
		method: "wallet.api.import_api.parse_statement",
		args: { name: frm.doc.name },
		freeze: true,
		freeze_message: __("Reading statement..."),
		callback: (r) => {
			if (!r.message) return;
			const m = r.message;
			frappe.show_alert({
				message: __("{0} rows: {1} new, {2} duplicates, {3} errors", [
					m.total_rows,
					m.new_rows,
					m.duplicate_rows,
					m.error_rows,
				]),
				indicator: m.error_rows ? "orange" : "green",
			});
			frm.reload_doc();
		},
	});
}

function commit_import(frm) {
	frappe.confirm(__("Create {0} transactions?", [frm.doc.new_rows]), () => {
		frappe.call({
			method: "wallet.api.import_api.commit_import",
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: __("Importing..."),
			callback: () => frm.reload_doc(),
		});
	});
}

function save_as_format(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Remember This Layout"),
		fields: [
			{
				fieldname: "format_name",
				fieldtype: "Data",
				label: __("Format Name"),
				reqd: 1,
			},
			{
				fieldname: "bank",
				fieldtype: "Link",
				label: __("Bank"),
				options: "Wallet Bank",
				reqd: 1,
			},
			{
				fieldtype: "HTML",
				options: `<p class="text-muted small">${__(
					"The next statement with the same column headers will skip the mapping step."
				)}</p>`,
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frappe.call({
				method: "wallet.api.import_api.save_as_format",
				args: { name: frm.doc.name, ...values },
				callback: () => {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function show_variance(frm) {
	if (frm.doc.balance_variance === null || frm.doc.balance_variance === undefined) return;
	if (!["Completed", "Partially Completed"].includes(frm.doc.status)) return;

	const clean = Math.abs(frm.doc.balance_variance) < 0.01;
	frm.dashboard.add_comment(
		clean
			? __("Reconciled: the computed balance matches the statement's closing balance.")
			: __(
					"Off by {0}. A row was probably missed, deduplicated too aggressively, or read from the wrong column.",
					[format_currency(frm.doc.balance_variance)]
			  ),
		clean ? "green" : "red",
		true
	);
}
