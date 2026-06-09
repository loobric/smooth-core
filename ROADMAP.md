# Roadmap

Planned and aspirational work, kept out of the README so feature claims there always
match the code. Sequencing follows the v2 milestones; epics track the detail:

## Milestone 1 — the sync loop (in progress)

The wear-offset round trip: a tool touched off at the machine shows up in CAM, with
provenance and an audit trail.

- Public facade API (`ToolRecord`, `Machine`, `ToolTableEntry`, `Library`) — #3, #4
- Identity binding between controller tool tables and tool records, with a review inbox — #5, #6
- Conflict freeze and resolution (no silent overwrites) — #7
- Docker packaging (x86 + ARM) and a sub-30-minute quickstart — #8

## Milestone 2 — importers (epic #11)

User-side importers for the formats hobbyists already have, including feeds & speeds
where the source carries them:

- Vectric tool databases (`.tool` / `.vtdb`)
- Fusion 360 `.tools` libraries
- Carbide Create CSV

## Milestone 3 — cutting parameters & sharing (epic #12)

- Feeds & speeds preset records (engineering values: surface speed, chipload — aligned
  with FreeCAD's F&S architecture)
- Preset sync via `.fctb`
- Community library publishing
- Public sandbox + invite-gated hosted instances

## Milestone 4 — small-shop phase (epic #13)

- ISO 13399 / GTC catalog import (pragmatic P21 property subset)
- FreeCAD F&S resolver provider backed by Smooth
- Manufacturer catalog publishing
- Hosted offering general availability

## Exploratory / unscheduled

- STEP-NC and MTConnect alignment
- Webhook/event system for external integrations
- Rate limiting and hardening for public-facing deployments
- PostgreSQL as a supported production backend
