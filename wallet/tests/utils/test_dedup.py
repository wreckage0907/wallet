# Copyright (c) 2026, girish.raghav2004@gmail.com and contributors
# For license information, please see license.txt

"""Tests for `wallet.utils.dedup`.

Split by what each tier needs. `normalize`, `content_key` and the reference-number and
running-balance tiers of `build_dedup_hash` are pure, so they get a `UnitTestCase`. Only
`occurrence_index` - and the ordinal tier that falls back to it - reads the database.

Nothing here pins a hash to a literal digest. What matters is which inputs collide and
which do not; the digest itself is an implementation detail, and pinning it would turn a
change of hash function into a test rewrite rather than the deliberate re-import it is.
"""

import datetime

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase, set_user

from wallet.tests.fixtures import commit, make_account, make_transaction, make_user, purge
from wallet.utils.dedup import (
	build_dedup_hash,
	content_key,
	find_duplicate,
	normalize,
	occurrence_index,
)

ACCOUNT = "acct-one"
OTHER_ACCOUNT = "acct-two"


class TestNormalize(UnitTestCase):
	def test_case_is_folded(self):
		self.assertEqual(normalize("UPI-SWIGGY"), normalize("upi-swiggy"))

	def test_punctuation_becomes_whitespace_and_collapses(self):
		"""Banks reformat their own narrations between exports - a stray slash, a doubled
		space - and an unnormalised hash would call that a new transaction."""
		self.assertEqual(normalize("UPI/SWIGGY/12345"), "upi swiggy 12345")
		self.assertEqual(normalize("UPI  -  SWIGGY"), "upi swiggy")

	def test_leading_and_trailing_whitespace_goes(self):
		self.assertEqual(normalize("  SALARY  "), "salary")

	def test_nothing_normalises_to_the_empty_string(self):
		for value in (None, "", "   "):
			with self.subTest(value=value):
				self.assertEqual(normalize(value), "")

	def test_non_strings_are_coerced(self):
		"""Statement cells arrive as whatever the reader found in them."""
		self.assertEqual(normalize(12345), "12345")


class TestContentKey(UnitTestCase):
	def test_the_date_is_reduced_to_a_day(self):
		"""A datetime and a date for the same day are the same transaction."""
		self.assertEqual(
			content_key(ACCOUNT, datetime.datetime(2026, 4, 1, 13, 45), -250, "Coffee"),
			content_key(ACCOUNT, datetime.date(2026, 4, 1), -250, "Coffee"),
		)

	def test_date_strings_and_date_objects_agree(self):
		self.assertEqual(
			content_key(ACCOUNT, "2026-04-01", -250, "Coffee"),
			content_key(ACCOUNT, datetime.date(2026, 4, 1), -250, "Coffee"),
		)

	def test_the_amount_is_fixed_to_two_places(self):
		"""Float noise out of Excel must not fingerprint as a different row."""
		self.assertEqual(
			content_key(ACCOUNT, "2026-04-01", -250.0, "Coffee"),
			content_key(ACCOUNT, "2026-04-01", -250.004, "Coffee"),
		)

	def test_the_sign_is_part_of_the_key(self):
		"""250 in and 250 out on the same day are different transactions."""
		self.assertNotEqual(
			content_key(ACCOUNT, "2026-04-01", 250, "Coffee"),
			content_key(ACCOUNT, "2026-04-01", -250, "Coffee"),
		)


class TestBuildDedupHash(UnitTestCase):
	"""The two tiers that never touch the database."""

	def test_a_reference_number_is_the_whole_fingerprint(self):
		"""Tier one: a UTR or cheque number is already unique per account, so nothing else
		is allowed to move the hash. A bank that restates a narration or corrects a value
		date must not produce a second copy of the same payment."""
		first = build_dedup_hash(ACCOUNT, "2026-04-01", -250, "Coffee", reference_number="UTR123")
		second = build_dedup_hash(ACCOUNT, "2026-04-02", -999, "COFFEE SHOP LTD", reference_number="UTR123")

		self.assertEqual(first, second)

	def test_a_reference_number_is_normalised_before_use(self):
		self.assertEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -250, reference_number="UTR-123"),
			build_dedup_hash(ACCOUNT, "2026-04-01", -250, reference_number=" utr 123 "),
		)

	def test_different_reference_numbers_never_collide(self):
		self.assertNotEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -250, reference_number="UTR123"),
			build_dedup_hash(ACCOUNT, "2026-04-01", -250, reference_number="UTR124"),
		)

	def test_a_blank_reference_number_falls_through_to_the_content_tiers(self):
		"""Otherwise every row of a statement with an empty reference column would share
		one fingerprint and all but the first would be dropped."""
		self.assertNotEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -250, "Coffee", reference_number="", balance_after=1),
			build_dedup_hash(ACCOUNT, "2026-04-01", -250, "Coffee", reference_number="   ", balance_after=2),
		)

	def test_the_running_balance_separates_two_identical_payments(self):
		"""Tier two, and the reason this app leans on the balance column: two genuine 50
		rupee payments to the same merchant on the same day differ only in the balance they
		leave behind, and that separates them with no counting and no dependence on row
		order."""
		self.assertNotEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", balance_after=1000),
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", balance_after=950),
		)

	def test_the_same_row_re_imported_fingerprints_the_same(self):
		"""The point of the whole module: overlapping statements must not double up."""
		self.assertEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", balance_after=950),
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", balance_after=950),
		)

	def test_a_reformatted_narration_still_fingerprints_the_same(self):
		self.assertEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "UPI/CHAI/99", balance_after=950),
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "upi  chai  99", balance_after=950),
		)

	def test_a_zero_running_balance_still_counts_as_a_balance(self):
		"""`0.0` is falsy; treating it as absent would drop an emptied account down to the
		weakest tier."""
		self.assertNotEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", balance_after=0),
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", occurrence=0),
		)

	def test_an_explicit_occurrence_separates_rows_in_one_file(self):
		"""Tier three. The importer counts occurrences within the file it is staging,
		because a database count alone would give two identical rows in the same statement
		the same ordinal, the same hash, and silently drop the second."""
		self.assertNotEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Cash", occurrence=0),
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Cash", occurrence=1),
		)

	def test_the_account_is_part_of_every_fingerprint(self):
		"""Which is also why a collision across two holders is impossible: accounts are
		owner-scoped, so the account component can never be shared."""
		self.assertNotEqual(
			build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", balance_after=950),
			build_dedup_hash(OTHER_ACCOUNT, "2026-04-01", -50, "Chai", balance_after=950),
		)

	def test_the_tiers_do_not_bleed_into_one_another(self):
		"""Same content, three different discriminators, three different fingerprints."""
		by_reference = build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", reference_number="R1")
		by_balance = build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", balance_after=950)
		by_occurrence = build_dedup_hash(ACCOUNT, "2026-04-01", -50, "Chai", occurrence=0)

		self.assertEqual(len({by_reference, by_balance, by_occurrence}), 3)


class TestOccurrenceIndex(IntegrationTestCase):
	"""The one part of the module that reads the database."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.user = make_user("dedup-holder@example.com")
		purge(cls.user)

		with set_user(cls.user):
			cls.account = make_account("Dedup Savings")
			cls.other_account = make_account("Dedup Current")
			# Two identical rows, plus near-misses on every component of the key.
			cls.first = make_transaction(cls.account, "2026-04-01", "Out", 50, "Chai")
			cls.second = make_transaction(cls.account, "2026-04-01", "Out", 50, "chai!!")
			make_transaction(cls.account, "2026-04-02", "Out", 50, "Chai")
			make_transaction(cls.account, "2026-04-01", "Out", 60, "Chai")
			make_transaction(cls.account, "2026-04-01", "In", 50, "Chai")
			make_transaction(cls.account, "2026-04-01", "Out", 50, "Samosa")
			make_transaction(cls.other_account, "2026-04-01", "Out", 50, "Chai")

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.user)
		commit()
		super().tearDownClass()

	def key(self, account=None):
		return content_key(account or self.account, "2026-04-01", -50, "Chai")

	def test_it_counts_only_rows_matching_every_component(self):
		"""A different date, amount, sign, description or account is a different row."""
		self.assertEqual(occurrence_index(*self.key()), 2)

	def test_descriptions_are_compared_normalised(self):
		""" "chai!!" is the same narration as "Chai", which is why the count is 2 above."""
		self.assertEqual(occurrence_index(*content_key(self.account, "2026-04-01", -50, "  CHAI  ")), 2)

	def test_rows_on_another_account_are_not_counted(self):
		self.assertEqual(occurrence_index(*self.key(self.other_account)), 1)

	def test_exclude_leaves_a_row_out_of_its_own_count(self):
		"""So re-deriving an ordinal for an existing row does not count that row twice."""
		self.assertEqual(occurrence_index(*self.key(), exclude=self.first), 1)

	def test_a_key_nothing_matches_counts_zero(self):
		self.assertEqual(
			occurrence_index(*content_key(self.account, "2026-04-01", -50, "Nothing Like This")), 0
		)

	def test_the_ordinal_tier_derives_its_discriminator_from_the_database(self):
		"""With no reference number, no running balance and no explicit occurrence, the
		hash has to come from a count - and a third identical row must not collide with the
		ordinal the first two already used."""
		derived = build_dedup_hash(self.account, "2026-04-01", -50, "Chai")
		explicit_first = build_dedup_hash(self.account, "2026-04-01", -50, "Chai", occurrence=0)
		explicit_third = build_dedup_hash(self.account, "2026-04-01", -50, "Chai", occurrence=2)

		self.assertEqual(derived, explicit_third)
		self.assertNotEqual(derived, explicit_first)


class TestFindDuplicate(IntegrationTestCase):
	"""The lookup every manual write path runs before inserting.

	`dedup_hash` is a UNIQUE column, so an entry that fingerprints identically to an
	existing row raises a MariaDB 1062 - an error code, reaching whoever is holding the
	phone. This is what turns that into the name of the row it collided with.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.holder = make_user("dedup-dup-holder@example.com")
		cls.other = make_user("dedup-dup-other@example.com")
		purge(cls.holder, cls.other)

		with set_user(cls.holder):
			cls.account = make_account("Dup Savings")
			cls.with_reference = make_transaction(
				cls.account, "2026-04-01", "Out", 250, "Chai", reference_number="UTR-DUP-1"
			)
			cls.without_reference = make_transaction(cls.account, "2026-04-02", "Out", 60, "Samosa")

		with set_user(cls.other):
			# Same account *name*, same narration, same amount, same day. Only the owner
			# differs, and `account` is part of every fingerprint - so the hashes cannot
			# collide even before the query's owner condition is reached.
			cls.other_account = make_account("Dup Savings")
			make_transaction(
				cls.other_account, "2026-04-01", "Out", 250, "Chai", reference_number="UTR-DUP-1"
			)

		commit()

	@classmethod
	def tearDownClass(cls):
		purge(cls.holder, cls.other)
		commit()
		super().tearDownClass()

	def test_a_repeated_reference_number_is_found(self):
		with set_user(self.holder):
			found = find_duplicate(self.account, "2026-04-01", -250, "Chai", "UTR-DUP-1")

		self.assertIsNotNone(found)
		self.assertEqual(found["id"], self.with_reference)
		self.assertEqual(found["posting_date"], "2026-04-01")
		self.assertEqual(found["amount"], 250)

	def test_the_reference_number_alone_decides_the_top_tier(self):
		"""Tier one hashes the reference and nothing else, so a re-keyed entry that gets
		the date and the amount wrong still has to be caught."""
		with set_user(self.holder):
			found = find_duplicate(self.account, "2026-09-09", -999, "Something else", "UTR-DUP-1")

		self.assertEqual(found["id"], self.with_reference)

	def test_a_genuinely_new_entry_is_not_a_duplicate(self):
		with set_user(self.holder):
			self.assertIsNone(find_duplicate(self.account, "2026-04-03", -75, "Vada pav"))

	def test_a_repeat_without_a_reference_is_allowed_through(self):
		"""Two identical cash payments on one day are two real transactions. The ordinal
		tier exists to keep them distinct, and this check must not undo it."""
		with set_user(self.holder):
			self.assertIsNone(find_duplicate(self.account, "2026-04-02", -60, "Samosa"))

	def test_another_holders_row_is_never_reported(self):
		"""Handed the other holder's own account docname, so the fingerprints are
		identical and the first line of defence - `account` being part of every hash - does
		not apply. What is left is the owner condition on `frappe.get_list`, which is
		exactly the thing being tested."""
		with set_user(self.holder):
			found = find_duplicate(self.other_account, "2026-04-01", -250, "Chai", "UTR-DUP-1")

		self.assertIsNone(found)
