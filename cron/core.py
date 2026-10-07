"""A five field cron expression parser and next fire time calculator.

The kernel is pure and deterministic: it never reads the system clock,
never touches the disk and never talks to the network.  Callers hand it a
naive *local* datetime, the moment their own wall clock shows, and get the
next matching local datetime back, so the arithmetic stays independent of
any timezone database.

An expression has five whitespace separated fields::

    minute   hour   day of month   month   day of week

A field holds a comma separated list of items, and an item is

    *        every value of the field
    n        a single value
    a-b      an inclusive range from a up to b
    */n      every n-th value of the field, counted from its lowest value
    a-b/n    every n-th value of the range, counted from a
    a/n      every n-th value from a up to the top of the field

Month names (JAN..DEC) and day of week names (SUN..SAT) may be written
instead of numbers.  Weekdays are numbered 0 to 6 with 0 standing for
Sunday, and 7 is accepted as another spelling of Sunday.  The two day
fields also accept ``?``, which carries no information and means exactly
the same as ``*``; in the other fields ``?`` is a mistake and is rejected.

A day field counts as *unrestricted* only when it is exactly ``*`` or
``?``; a range, a list or a step is a restriction.  When both day fields
are restricted a day is selected by *either* of them -- "the 1st, and also
every Monday" -- otherwise the restricted field alone selects the day.

``CronExpression.next_after`` returns the earliest local datetime the
expression fires on that is strictly later than the given moment; the
second and microsecond of the result are always zero.  When nothing
matches within the search horizon it returns ``None``.
"""

from datetime import date, datetime, time, timedelta

__all__ = ["CronError", "CronField", "CronExpression", "next_after", "parse_field"]

#: Month names accepted by the month field.
MONTH_NAMES = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

#: Day of week names accepted by the day of week field, Sunday first.
DOW_NAMES = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}

#: How far ``next_after`` looks for a match before giving up.
HORIZON_DAYS = 366 * 40

#: Length of every month in an ordinary year.
_MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

class CronError(ValueError):
    """Raised when an expression or a field of it cannot be parsed."""


def _field_number(token, name, low, high, names):
    """Read one number of a field and check that it is inside the field."""
    text = token.strip().upper()
    if names is not None and text in names:
        return names[text]
    if not text.isdigit():
        raise CronError("%s field: %r is not a number" % (name, token))
    value = int(text)
    if value < low or value > high:
        raise CronError("%s field: %r is outside %d..%d" % (name, token, low, high))
    return value


def _sunday_index(moment):
    """Weekday of *moment* counted from Sunday, so Sunday is 0."""
    return (moment.weekday() + 1) % 7


def _days_in_month(year, month):
    """Number of days in the given month of the given year."""
    if month == 2:
        if year % 400 == 0 or (year % 4 == 0 and year % 100 != 0):
            return 29
        return 28
    return _MONTH_LENGTHS[month - 1]


def _next_month(year, month):
    """The year and month that follow the given one."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


class CronField:
    """One parsed field: the values it accepts and whether it is a star."""

    __slots__ = ("name", "low", "high", "values", "star")

    def __init__(self, name, low, high, values, star):
        self.name = name
        self.low = low
        self.high = high
        self.values = frozenset(values)
        self.star = star

    def __contains__(self, value):
        return value in self.values

    def sorted_values(self):
        """The accepted values in ascending order."""
        return sorted(self.values)

    def __repr__(self):
        return "CronField(%r, %r, star=%r)" % (self.name, self.sorted_values(), self.star)


def parse_field(spec, name, low, high, names=None, allow_question=False, fold_sunday=False):
    """Parse a single field of an expression into a :class:`CronField`.

    ``low`` and ``high`` are the bounds of the field, ``names`` maps the
    symbolic spellings the field accepts, ``allow_question`` widens the
    grammar to ``?`` and ``fold_sunday`` widens the day of week field by
    the value 7.
    """
    if not isinstance(spec, str):
        raise CronError("%s field: expected a string, got %r" % (name, spec))
    if not spec:
        raise CronError("%s field is empty" % name)
    ceiling = high + 1 if fold_sunday else high
    values = set()
    star = spec == "*" or (allow_question and spec == "?")

    def add(value):
        if fold_sunday and value == high + 1:
            value = low
        values.add(value)

    for item in spec.split(","):
        if not item:
            raise CronError("%s field: %r has an empty item" % (name, spec))
        head, slash, tail = item.partition("/")
        if slash:
            step = _field_number(tail, name, 1, ceiling, None)
        else:
            step = 1
        if head == "*" or head == "?":
            if head == "?" and not allow_question:
                raise CronError("%s field does not accept '?'" % name)
            start, end = low, ceiling
        elif "-" in head:
            left, _, right = head.partition("-")
            start = _field_number(left, name, low, ceiling, names)
            end = _field_number(right, name, low, ceiling, names)
            if end < start:
                raise CronError(
                    "%s field: %r is a reversed range" % (name, head)
                )
        else:
            start = _field_number(head, name, low, ceiling, names)
            end = ceiling if slash else start
        for value in range(start, end + 1, step):
            add(value)
    return CronField(name, low, high, values, star)


class CronExpression:
    """A parsed five field expression."""

    def __init__(self, expression):
        if not isinstance(expression, str):
            raise CronError("expression: expected a string, got %r" % (expression,))
        parts = expression.split()
        if len(parts) != 5:
            raise CronError("expected 5 fields, got %d in %r" % (len(parts), expression))
        self.expression = expression
        self.minute = parse_field(parts[0], "minute", 0, 59)
        self.hour = parse_field(parts[1], "hour", 0, 23)
        self.day_of_month = parse_field(parts[2], "day of month", 1, 31, allow_question=True)
        self.month = parse_field(parts[3], "month", 1, 12, MONTH_NAMES)
        self.day_of_week = parse_field(
            parts[4], "day of week", 0, 6, DOW_NAMES, allow_question=True, fold_sunday=True
        )
        self.fields = (self.minute, self.hour, self.day_of_month, self.month, self.day_of_week)

    def __repr__(self):
        return "CronExpression(%r)" % (self.expression,)

    def _day_matches(self, moment):
        """True when *moment* falls on a day the expression fires on."""
        dom_ok = moment.day in self.day_of_month
        dow_ok = _sunday_index(moment) in self.day_of_week
        if self.day_of_month.star or self.day_of_week.star:
            return dom_ok and dow_ok
        return dom_ok or dow_ok

    def matches(self, moment):
        """True when *moment* falls on a minute the expression fires on."""
        if not isinstance(moment, datetime):
            raise CronError("matches expects a datetime, got %r" % (moment,))
        if moment.minute not in self.minute:
            return False
        if moment.hour not in self.hour:
            return False
        if moment.month not in self.month:
            return False
        return self._day_matches(moment)

    def next_after(self, now):
        """Return the fire time that follows *now*, or ``None``.

        The result is strictly later than *now* and its seconds and
        microseconds are zero.  ``None`` means the expression does not fire
        within the search horizon.
        """
        if not isinstance(now, datetime):
            raise CronError("next_after expects a datetime, got %r" % (now,))
        if now.tzinfo is not None:
            raise CronError("next_after works on naive local datetimes")
        horizon = (now + timedelta(days=HORIZON_DAYS)).date()
        hours = self.hour.sorted_values()
        minutes = self.minute.sorted_values()
        year, month = now.year, now.month
        while True:
            if month in self.month:
                for number in range(1, _days_in_month(year, month) + 1):
                    day = date(year, month, number)
                    if day < now.date():
                        continue
                    if not self._day_matches(day):
                        continue
                    for hour in hours:
                        for minute in minutes:
                            candidate = datetime.combine(day, time(hour, minute))
                            if candidate > now:
                                return candidate
            year, month = _next_month(year, month)
            if date(year, month, 1) > horizon:
                return None


def next_after(expression, now):
    """Parse *expression* and return its next fire time after *now*."""
    return CronExpression(expression).next_after(now)
