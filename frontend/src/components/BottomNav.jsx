import { NavLink } from "react-router-dom";
import { Home, ListOrdered, Settings2 } from "lucide-react";

// Add and Import land in phase 6. They are omitted rather than shown as dead tabs:
// the wildcard route would bounce both straight back to the dashboard, which reads as
// a broken button.
const TABS = [
	{ to: "/", icon: Home, label: "Home", end: true },
	{ to: "/transactions", icon: ListOrdered, label: "Activity" },
	{ to: "/settings", icon: Settings2, label: "More" },
];

export default function BottomNav() {
	return (
		<nav
			className="safe-bottom fixed inset-x-0 bottom-0 z-50 border-t backdrop-blur"
			style={{ borderColor: "var(--border)", background: "color-mix(in srgb, var(--surface) 92%, transparent)" }}
		>
			<div className="mx-auto flex w-full max-w-lg items-stretch justify-around px-2">
				{TABS.map(({ to, icon: Icon, label, end, primary }) => (
					<NavLink
						key={to}
						to={to}
						end={end}
						// 44px minimum touch target — anything smaller is a miss on a phone.
						className="flex min-h-[56px] min-w-[56px] flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors"
						style={({ isActive }) => ({
							color: isActive ? "var(--brand)" : "var(--text-muted)",
						})}
					>
						{primary ? (
							<span
								className="flex h-9 w-9 items-center justify-center rounded-full"
								style={{ background: "var(--brand)", color: "var(--surface)" }}
							>
								<Icon size={20} strokeWidth={2.5} />
							</span>
						) : (
							<Icon size={20} />
						)}
						<span>{label}</span>
					</NavLink>
				))}
			</div>
		</nav>
	);
}
