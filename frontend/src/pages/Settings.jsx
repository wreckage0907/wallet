import { useState } from "react";
import { Bot, ExternalLink, RefreshCw, RotateCcw } from "lucide-react";
import { useFrappeAuth, useFrappeGetCall, useFrappePostCall } from "frappe-react-sdk";

import { Card, Screen } from "../components/ui.jsx";
import { M } from "../lib/api.js";

function ActionRow({ icon: Icon, label, hint, onClick, busy, danger }) {
	return (
		<button
			onClick={onClick}
			disabled={busy}
			className="flex min-h-[56px] w-full items-center gap-3 px-4 py-3 text-left disabled:opacity-50"
		>
			<Icon
				size={18}
				className={`${busy ? "animate-spin" : ""} ${danger ? "text-ink-red-4" : "text-ink-gray-5"}`}
			/>
			<span className="min-w-0 flex-1">
				<span className="block text-sm font-medium text-ink-gray-9">{label}</span>
				{hint && <span className="block text-xs text-ink-gray-5">{hint}</span>}
			</span>
		</button>
	);
}

// The user's half of the MCP write gate (wallet/mcp/gate.py). The site half is an
// administrator's, in Wallet Settings, so it is reported here but not switchable.
function agentHint(access) {
	if (!access) return "Checking…";
	if (!access.user) return "Off: agents you connect can only read";
	if (!access.site) return "On for you, but an administrator has turned it off for this site";
	return "On: agents you connect can record and change transactions";
}

function AgentAccessRow({ onError }) {
	const { data, mutate } = useFrappeGetCall(M.mcpAccess, undefined, undefined, {
		revalidateOnFocus: false,
	});
	const { call, loading } = useFrappePostCall(M.setMcpWrites);
	const access = data?.message;
	const on = Boolean(access?.user);

	const toggle = async () => {
		try {
			const result = await call({ enabled: !on });
			mutate({ message: result.message }, false);
		} catch (error) {
			onError(error?.message || "That did not work.");
		}
	};

	return (
		<button
			role="switch"
			aria-checked={on}
			onClick={toggle}
			disabled={!access || loading}
			className="flex min-h-[56px] w-full items-center gap-3 px-4 py-3 text-left disabled:opacity-50"
		>
			<Bot size={18} className="text-ink-gray-5" />
			<span className="min-w-0 flex-1">
				<span className="block text-sm font-medium text-ink-gray-9">Let AI agents make changes</span>
				<span className="block text-xs text-ink-gray-5">{agentHint(access)}</span>
			</span>
			<span
				aria-hidden="true"
				className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${
					on ? "bg-surface-gray-7" : "bg-surface-gray-3"
				}`}
			>
				<span
					className={`absolute top-0.5 h-5 w-5 rounded-full bg-surface-white shadow transition-all ${
						on ? "left-[18px]" : "left-0.5"
					}`}
				/>
			</span>
		</button>
	);
}

export default function Settings() {
	const { currentUser } = useFrappeAuth();
	const [note, setNote] = useState(null);

	const { call: rebuild, loading: rebuilding } = useFrappePostCall(M.rebuild);
	const { call: restore, loading: restoring } = useFrappePostCall(M.restoreCategories);

	const run = async (fn, describe) => {
		setNote(null);
		try {
			const result = await fn({});
			setNote(describe(result?.message || {}));
		} catch (error) {
			setNote(error?.message || "That did not work.");
		}
	};

	return (
		<Screen title="More">
			<Card className="!p-0 overflow-hidden">
				<div className="px-4 py-3">
					<p className="text-xs text-ink-gray-5">Signed in as</p>
					<p className="truncate text-sm font-medium text-ink-gray-9">{currentUser}</p>
				</div>
			</Card>

			<Card className="!p-0 overflow-hidden">
				<ActionRow
					icon={RefreshCw}
					label="Recalculate balances"
					hint="Refreshes the cached figure on every account"
					busy={rebuilding}
					onClick={() => run(rebuild, (r) => `Rebuilt ${r.rebuilt ?? 0} account balances.`)}
				/>
				<div className="border-t border-outline-gray-2" />
				<ActionRow
					icon={RotateCcw}
					label="Restore default categories"
					hint="Brings back deleted defaults; renames are left alone"
					busy={restoring}
					onClick={() =>
						run(restore, (r) =>
							r.restored ? `Restored ${r.restored} categories.` : "Nothing was missing."
						)
					}
				/>
			</Card>

			{note && <Card className="text-sm text-ink-gray-5">{note}</Card>}

			<Card className="!p-0 overflow-hidden">
				<AgentAccessRow onError={setNote} />
			</Card>

			<Card className="!p-0 overflow-hidden">
				<a href="/app/wallet" className="flex min-h-[56px] items-center gap-3 px-4 py-3">
					<ExternalLink size={18} className="text-ink-gray-5" />
					<span className="min-w-0 flex-1">
						<span className="block text-sm font-medium text-ink-gray-9">Open full app</span>
						<span className="block text-xs text-ink-gray-5">
							Accounts, categories, rules and statement imports
						</span>
					</span>
				</a>
			</Card>
		</Screen>
	);
}
