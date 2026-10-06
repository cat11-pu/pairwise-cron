# cron

A five field cron expression parser and next fire time calculator written with
the Python standard library only. There is nothing to install and no third
party dependency.

A naive local `datetime` goes in and the next matching local `datetime` comes
out; the kernel never reads the system clock and never touches the network.

## What is inside

* `cron/core.py` - the field parser and the fire time calculator.
* `tests/test_core.py` - the acceptance tests for the kernel.

## Public interface

```python
from cron import CronExpression, parse_field

expression = CronExpression("*/15 9-17 * * 1-5")
expression.next_after(datetime(2025, 3, 10, 10, 0))   # a datetime, or None
expression.matches(datetime(2025, 3, 10, 10, 15))     # True
parse_field("*/15", "minute", 0, 59).sorted_values()  # [0, 15, 30, 45]
```

* The five fields are `minute hour day-of-month month day-of-week`.
* A field takes a comma separated list of values, `a-b` ranges, `*/n` steps,
  `a-b/n` steps over a range and `a/n` steps counted from `a` up to the top of
  the field.
* Month names `JAN..DEC` and weekday names `SUN..SAT` are accepted. Weekdays are
  numbered from Sunday, so `0` and `7` are both Sunday.
* A day field that is exactly `*` or `?` puts no constraint on the day; every
  other spelling is a constraint, and two constrained day fields are combined
  with *or*.
* Malformed expressions raise `CronError`, a subclass of `ValueError`.

## Running the tests

From the project root:

    python3 -m unittest discover -s tests -v

All of the tests have to pass.
