# Label

Thin, and deliberately last: event category + colour via
`actions/calendar/categories.py`, task tags via `actions/todo/tagging.py`.
Both already existed; this stage only fixes their place in the flow.

Two invariants the category layer owns: adjacent events never share a colour,
and a hand-picked colour is never overridden.

## Status

Not yet dug into. Moved here for structure.
