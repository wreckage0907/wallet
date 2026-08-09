import { Loader2 } from "lucide-react";

export function Card({ children, className = "", ...rest }) {
	return (
		<div
			className={`rounded-2xl border p-4 ${className}`}
			style={{ background: "var(--surface)", borderColor: "var(--border)" }}
			{...rest}
		>
			{children}
		</div>
	);
}

export function Screen({ title, action, children }) {
	return (
		<>
			<header className="safe-top sticky top-0 z-40 px-4 pt-3 pb-2 backdrop-blur"
				style={{ background: "color-mix(in srgb, var(--surface-sunken) 88%, transparent)" }}>
				<div className="flex items-center justify-between gap-3">
					<h1 className="text-2xl font-bold tracking-tight">{title}</h1>
					{action}
				</div>
			</header>
			<div className="space-y-3 px-4 pt-1">{children}</div>
		</>
	);
}

export function Spinner({ label = "Loading" }) {
	return (
		<div
			className="flex items-center justify-center gap-2 py-12 text-sm"
			style={{ color: "var(--text-muted)" }}
		>
			<Loader2 size={16} className="animate-spin" />
			{label}
		</div>
	);
}

export function EmptyState({ icon: Icon, title, hint, action }) {
	return (
		<div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
			{Icon && (
				<span
					className="flex h-12 w-12 items-center justify-center rounded-2xl"
					style={{ background: "var(--surface-raised)", color: "var(--text-muted)" }}
				>
					<Icon size={22} />
				</span>
			)}
			<p className="font-semibold">{title}</p>
			{hint && (
				<p className="max-w-xs text-sm" style={{ color: "var(--text-muted)" }}>
					{hint}
				</p>
			)}
			{action}
		</div>
	);
}

export function ErrorNote({ error }) {
	if (!error) return null;
	const message =
		error?.message || error?.exception || error?._server_messages || "Something went wrong.";
	return (
		<Card className="text-sm" style={{ borderColor: "var(--color-money-out)" }}>
			<p className="font-semibold" style={{ color: "var(--color-money-out)" }}>
				Could not load
			</p>
			<p className="mt-1" style={{ color: "var(--text-muted)" }}>
				{String(message).slice(0, 300)}
			</p>
		</Card>
	);
}
