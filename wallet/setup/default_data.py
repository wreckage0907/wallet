# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Seed data shipped with the app, tuned for Indian personal finance.

These are *defaults*, not fixtures. They are inserted once (per user) and never
re-imported, so renaming or deleting a category sticks. `wallet.api.setup.restore_
default_categories` recreates anything you deleted and want back.
"""

#: (group name, icon, [child names])
EXPENSE_CATEGORIES: list[tuple[str, str, list[str]]] = [
	("Food & Dining", "🍽️", ["Restaurants", "Food Delivery", "Cafe & Snacks", "Office Canteen"]),
	("Groceries", "🛒", ["Supermarket", "Kirana / Local Store", "Milk & Dairy", "Vegetables & Fruits"]),
	(
		"Transport",
		"🚗",
		[
			"Fuel",
			"Cab & Auto",
			"Metro / Bus",
			"Train",
			"FASTag & Tolls",
			"Parking",
			"Vehicle Maintenance",
		],
	),
	(
		"Bills & Utilities",
		"💡",
		[
			"Electricity",
			"Water",
			"Gas / LPG",
			"Mobile Recharge",
			"Broadband / Wi-Fi",
			"DTH / Cable",
			"Maintenance Charges",
		],
	),
	("Rent & Housing", "🏠", ["House Rent", "Society Maintenance", "Home Repairs", "Domestic Help"]),
	("Shopping", "🛍️", ["Clothing & Footwear", "Electronics", "Online Shopping", "Home & Furniture"]),
	(
		"Health",
		"🏥",
		[
			"Doctor & Consultation",
			"Medicines / Pharmacy",
			"Diagnostics & Lab",
			"Hospital",
			"Gym & Fitness",
		],
	),
	("Education", "📚", ["Tuition & Fees", "Books & Stationery", "Courses & Certifications"]),
	("Entertainment", "🎬", ["Movies & Events", "Subscriptions (OTT)", "Games", "Hobbies"]),
	("Travel", "✈️", ["Flights", "Hotels", "Holiday Packages", "Local Travel"]),
	("Insurance", "🛡️", ["Life Insurance", "Health Insurance", "Vehicle Insurance"]),
	(
		"Investments",
		"📈",
		[
			"Mutual Funds / SIP",
			"Stocks",
			"PPF / EPF",
			"Fixed Deposit / RD",
			"NPS",
			"Gold",
			"Crypto",
		],
	),
	(
		"Loans & EMI",
		"🏦",
		[
			"Home Loan EMI",
			"Personal Loan EMI",
			"Vehicle Loan EMI",
			"Education Loan EMI",
			"Credit Card Payment",
		],
	),
	("Taxes", "🧾", ["Income Tax", "GST", "TDS", "Advance Tax"]),
	("Family & Gifts", "🎁", ["Gifts & Donations", "Children", "Parents & Family"]),
	("Personal Care", "💇", ["Salon & Grooming", "Cosmetics"]),
	(
		"Fees & Charges",
		"💸",
		["Bank Charges", "ATM Charges", "Late Fee", "Interest Charges", "Convenience Fee"],
	),
	("Cash Withdrawal", "🏧", []),
	("Miscellaneous", "❓", []),
]

INCOME_CATEGORIES: list[tuple[str, str, list[str]]] = [
	("Salary", "💰", []),
	("Business Income", "💼", []),
	("Freelance / Consulting", "🧑‍💻", []),
	("Interest Income", "🏦", ["Savings Interest", "FD / RD Interest"]),
	("Dividends", "📊", []),
	("Rental Income", "🏘️", []),
	("Refunds & Cashback", "↩️", []),
	("Gifts Received", "🎀", []),
	("Other Income", "➕", []),  # noqa: RUF001 - a category icon, not arithmetic
]

#: Transfers keep inter-account movement out of income and expense totals.
TRANSFER_CATEGORIES: list[tuple[str, str, list[str]]] = [
	("Self Transfer", "🔁", []),
	("Credit Card Bill Payment", "💳", []),
]

DEFAULT_CATEGORIES: dict[str, list[tuple[str, str, list[str]]]] = {
	"Expense": EXPENSE_CATEGORIES,
	"Income": INCOME_CATEGORIES,
	"Transfer": TRANSFER_CATEGORIES,
}


#: (rule name, pattern, target category, direction filter, priority)
#: Patterns are matched case-insensitively against the raw bank narration.
DEFAULT_RULES: list[tuple[str, str, str, str, int]] = [
	("Swiggy", "SWIGGY", "Food Delivery", "Out", 10),
	("Zomato", "ZOMATO", "Food Delivery", "Out", 10),
	("Blinkit / Zepto / Instamart", "BLINKIT|ZEPTO|INSTAMART|BIGBASKET", "Supermarket", "Out", 10),
	("Amazon", "AMAZON", "Online Shopping", "Out", 20),
	("Flipkart", "FLIPKART", "Online Shopping", "Out", 20),
	("Myntra / Ajio", "MYNTRA|AJIO", "Clothing & Footwear", "Out", 20),
	("Uber / Ola / Rapido", "UBER|OLA MONEY|OLACABS|RAPIDO", "Cab & Auto", "Out", 20),
	("IRCTC", "IRCTC", "Train", "Out", 20),
	("Fuel", "INDIAN ?OIL|IOCL|HPCL|BHARAT ?PETROLEUM|BPCL|PETROL|FUEL", "Fuel", "Out", 20),
	("FASTag", "FASTAG|NETC|TOLL", "FASTag & Tolls", "Out", 20),
	(
		"OTT subscriptions",
		"NETFLIX|SPOTIFY|HOTSTAR|PRIMEVIDEO|JIOCINEMA|SONYLIV",
		"Subscriptions (OTT)",
		"Out",
		20,
	),
	("Mobile recharge", "JIO|AIRTEL|VODAFONE|VI RECHARGE|BSNL", "Mobile Recharge", "Out", 30),
	("Electricity", "BESCOM|MSEB|TNEB|TANGEDCO|ADANI ?ELEC|ELECTRICITY|BSES", "Electricity", "Out", 30),
	("Broker / SIP", "GROWW|ZERODHA|KUVERA|UPSTOX|COIN|MUTUAL ?FUND|SIP ", "Mutual Funds / SIP", "Out", 30),
	("Loan EMI", "NACH|ECS|EMI|LOAN ?REPAY", "Loans & EMI", "Out", 40),
	("ATM withdrawal", "ATM ?WDL|CASH ?WDL|NWD|ATW", "Cash Withdrawal", "Out", 20),
	("Bank charges", "CHRG|CHARGES|GST ON|SMS ?CHG|AMC ", "Bank Charges", "Out", 40),
	("Insurance premium", "LIC |HDFC ?LIFE|ICICI ?PRU|POLICYBAZAAR|PREMIUM", "Life Insurance", "Out", 40),
	("Salary credit", "SALARY|SAL CR|SAL-|NEFT.*SALARY", "Salary", "In", 10),
	("Interest credit", "INT\\.PD|INTEREST ?CREDIT|CREDIT ?INTEREST", "Savings Interest", "In", 20),
	("Refund", "REFUND|REVERSAL|CASHBACK", "Refunds & Cashback", "In", 30),
]
