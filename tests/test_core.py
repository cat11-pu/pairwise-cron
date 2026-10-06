"""Behaviour tests for the cron expression kernel.

Run them from the project root:

    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cron.core import CronError, CronExpression, parse_field


def next_fire(expression, now):
    """Next fire time of *expression* strictly after *now*."""
    return CronExpression(expression).next_after(now)


def minute_values(spec):
    """Accepted values of a minute field, ascending."""
    return parse_field(spec, "minute", 0, 59).sorted_values()


class FieldExpansionTest(unittest.TestCase):
    def test_field_expansion_of_stars_ranges_and_steps(self):
        self.assertEqual(minute_values("*"), list(range(60)))
        self.assertEqual(minute_values("*/15"), [0, 15, 30, 45])
        self.assertEqual(minute_values("0-30/15"), [0, 15, 30])
        self.assertEqual(minute_values("45-59/5"), [45, 50, 55])
        self.assertEqual(minute_values("7"), [7])
        self.assertEqual(
            minute_values("5,10-12,20-24/2"), [5, 10, 11, 12, 20, 22, 24]
        )


class DayFieldTest(unittest.TestCase):
    def test_question_mark_means_a_star_in_the_day_fields(self):
        monday_noon = datetime(2025, 3, 3, 12, 0)
        self.assertEqual(next_fire("0 0 ? * 1", monday_noon), datetime(2025, 3, 10, 0, 0))
        self.assertEqual(
            next_fire("0 0 1 * ?", datetime(2025, 3, 5, 0, 0)), datetime(2025, 4, 1, 0, 0)
        )

    def test_sunday_can_be_written_as_zero_or_seven(self):
        saturday_noon = datetime(2025, 3, 8, 12, 0)
        self.assertEqual(next_fire("0 0 * * 7", saturday_noon), datetime(2025, 3, 9, 0, 0))
        self.assertEqual(next_fire("0 0 * * 0", saturday_noon), datetime(2025, 3, 9, 0, 0))
        self.assertEqual(next_fire("0 0 * * SUN", saturday_noon), datetime(2025, 3, 9, 0, 0))


class DayCombinationTest(unittest.TestCase):
    def test_day_of_month_and_day_of_week_are_combined_with_or(self):
        self.assertEqual(
            next_fire("0 0 13 * 5", datetime(2025, 3, 1, 0, 0)), datetime(2025, 3, 7, 0, 0)
        )
        self.assertEqual(
            next_fire("13 9 1 * 5", datetime(2025, 6, 2, 0, 0)), datetime(2025, 6, 6, 9, 13)
        )

    def test_day_of_week_numbers_and_names_are_sunday_based(self):
        after_the_slot = datetime(2025, 3, 5, 10, 0)
        self.assertEqual(
            next_fire("30 9 * * MON", after_the_slot), datetime(2025, 3, 10, 9, 30)
        )
        self.assertEqual(
            next_fire("30 9 * * 1", after_the_slot), datetime(2025, 3, 10, 9, 30)
        )
        self.assertEqual(
            next_fire("0 12 * * SUN", datetime(2025, 3, 5, 0, 0)), datetime(2025, 3, 9, 12, 0)
        )
        self.assertEqual(
            next_fire("0 12 * * 0", datetime(2025, 3, 5, 0, 0)), datetime(2025, 3, 9, 12, 0)
        )


class CalendarBoundaryTest(unittest.TestCase):
    def test_leap_days_and_days_no_month_has(self):
        self.assertEqual(
            next_fire("0 0 29 2 *", datetime(1999, 3, 1, 0, 0)), datetime(2000, 2, 29, 0, 0)
        )
        self.assertEqual(
            next_fire("0 0 29 2 *", datetime(2023, 1, 1, 0, 0)), datetime(2024, 2, 29, 0, 0)
        )
        self.assertEqual(
            next_fire("0 0 31 12 *", datetime(2025, 1, 1, 0, 0)), datetime(2025, 12, 31, 0, 0)
        )
        self.assertIsNone(next_fire("0 0 31 4 *", datetime(2025, 1, 1, 0, 0)))
        self.assertIsNone(next_fire("0 0 30 2 *", datetime(2025, 1, 1, 0, 0)))


class NextFireTest(unittest.TestCase):
    def test_next_fire_after_an_exact_minute(self):
        self.assertEqual(
            next_fire("*/15 * * * *", datetime(2025, 3, 10, 10, 0, 0)),
            datetime(2025, 3, 10, 10, 15, 0),
        )

    def test_next_fire_after_a_stepped_range(self):
        self.assertEqual(
            next_fire("0-30/15 * * * *", datetime(2025, 3, 10, 10, 0, 30)),
            datetime(2025, 3, 10, 10, 15, 0),
        )

    def test_next_fire_is_strictly_later_and_skips_missed_moments(self):
        self.assertEqual(
            next_fire("* * * * *", datetime(2025, 3, 10, 10, 0, 0)),
            datetime(2025, 3, 10, 10, 1, 0),
        )
        self.assertEqual(
            next_fire("* * * * *", datetime(2025, 3, 10, 10, 42, 17)),
            datetime(2025, 3, 10, 10, 43, 0),
        )
        self.assertEqual(
            next_fire("0 12 * * *", datetime(2025, 3, 10, 15, 0, 0)),
            datetime(2025, 3, 11, 12, 0, 0),
        )
        self.assertEqual(
            next_fire("0 0 1 * *", datetime(2025, 3, 1, 0, 0, 0)),
            datetime(2025, 4, 1, 0, 0, 0),
        )
        self.assertEqual(
            next_fire("0 8 * * 1-5", datetime(2025, 3, 14, 9, 0, 0)),
            datetime(2025, 3, 17, 8, 0, 0),
        )
        for base in (
            datetime(2025, 3, 10, 10, 0, 0),
            datetime(2025, 3, 10, 23, 59, 59),
            datetime(2025, 12, 31, 23, 59, 0),
        ):
            moment = next_fire("* * * * *", base)
            self.assertGreater(moment, base)
            self.assertEqual((moment.second, moment.microsecond), (0, 0))
        expression = CronExpression("*/20 2,14 * * *")
        moment = expression.next_after(datetime(2025, 3, 10, 15, 0, 0))
        self.assertTrue(expression.matches(moment))
        self.assertEqual(moment, datetime(2025, 3, 11, 2, 0, 0))


class ErrorHandlingTest(unittest.TestCase):
    def test_malformed_expressions_raise_cron_error(self):
        for expression in (
            "",
            "* * * *",
            "* * * * * *",
            "60 * * * *",
            "* 24 * * *",
            "* * 0 * *",
            "* * 32 * *",
            "* * * 13 *",
            "* * * * 8",
            "*/0 * * * *",
            "30-10 * * * *",
            "? * * * *",
            "* ? * * *",
            "* * * ? *",
            "1-2-3 * * * *",
            "a * * * *",
            "* * * * abc",
        ):
            with self.subTest(expression=expression):
                with self.assertRaises(CronError):
                    CronExpression(expression)


if __name__ == "__main__":
    unittest.main()
