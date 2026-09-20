import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

import BottomNav from "./components/BottomNav.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Accounts from "./pages/Accounts.jsx";
import AccountDetail from "./pages/AccountDetail.jsx";
import Transactions from "./pages/Transactions.jsx";
import AddTransaction from "./pages/AddTransaction.jsx";
import Settings from "./pages/Settings.jsx";
import { useEnsureSetup } from "./lib/api.js";

export default function App() {
	const { call: ensureSetup } = useEnsureSetup();

	// Users who existed before the app was installed never fired the User.after_insert
	// hook, so they have no categories. This is the lazy catch-up; it is a no-op once
	// they have any.
	useEffect(() => {
		ensureSetup().catch(() => {});
	}, [ensureSetup]);

	return (
		<div className="min-h-full" style={{ background: "var(--surface-sunken)" }}>
			<main className="mx-auto w-full max-w-lg pb-24">
				<Routes>
					<Route path="/" element={<Dashboard />} />
					<Route path="/accounts" element={<Accounts />} />
					<Route path="/accounts/:name" element={<AccountDetail />} />
					<Route path="/transactions" element={<Transactions />} />
					<Route path="/add" element={<AddTransaction />} />
					<Route path="/settings" element={<Settings />} />
					<Route path="*" element={<Navigate to="/" replace />} />
				</Routes>
			</main>
			<BottomNav />
		</div>
	);
}
