# Basic object control — API 1.0

The Blender server advertises five mutation tools. Each requires the current
session and revision, consumes one revision on handler entry (including rejected
attempts), and expires all selection handles. Envelope/schema failures and stale
state rejections do not consume a revision. All tools return
`result: {"object_id": "<UUID>"}` and fill `created_ids`, `modified_ids`,
`deleted_ids` as described below. These are explicit object changes, not a full
scene diff. With the recovery backend enabled, these tools support checkpoint
rollback; see [RECOVERY.md](RECOVERY.md) for transactions and bounded scene diffs.

All operations run synchronously on Blender's main thread using the data API.
They require Object mode and an editable current scene. Referenced targets must
belong to the current scene; names are labels and UUIDs are addresses. Tools do
not select objects, change the active object, or enter Edit mode. Removed targets
naturally leave selection and active-object state if they were selected/active.

## `object.create_primitive`

Required: `primitive`, one of `CUBE`, `PLANE`, `CYLINDER`, `CONE`.
Optional: `name`, `size` (default 2), `unit` (`m`, `cm`, `mm`; default `m`),
`location` (three lengths), `rotation` (three XYZ Euler angles in degrees),
`scale` (three nonzero factors), `segments` (3–256; default 32).
`segments` is supported only for cylinders and cones. Names accept 1–63 characters;
Blender may suffix a name to avoid collisions.

Size means cube/plane side length or cylinder/cone diameter and height before
transform. Size must be between 1e-9 and 1e6 in the chosen unit. The plane lies in
XY; cylinders and cones align to Z; all primitives are centered on the origin
before transform. Solids use outward winding with n-gon end caps and no UVs or
materials. Cone has one tip. Low/odd segment counts may have measured bounds
smaller than the nominal diameter, since vertices sample a circular profile.
New mesh and object data are independent, linked to the current scene's root
collection, with fresh persistent UUID. `created_ids` contains that UUID.

## `object.transform`

Required: `object_id`. Supply at least one of `location`, `rotation`, `scale`.
Optional `unit` controls location lengths. Components are absolute parent-local
values, not incremental edits or world dimensions. Rotation uses XYZ degrees;
location is normalized to meters. Omitted components retain the effective local
basis. Delta transforms are baked into the basis and reset; rotation mode becomes
XYZ. Parenting's inverse matrix remains unchanged. Negative scale is supported;
zero scale is rejected. Location values are bounded to ±1e9, angles to ±360000,
and scale factors to ±1e6.

Constraints, animation data (including drivers), rigid-body state and bone/vertex
parenting are rejected to prevent evaluation from overriding the requested pose.
Transform locks are UI restrictions and do not prevent explicit API edits.
`modified_ids` contains the target UUID.

## `object.duplicate`

Required: `object_id`. Optional: `name`, `linked_data` (default false).
Copies object properties, modifiers, constraints, animation references, parent and
transform. By default object data is copied; `linked_data: true` intentionally
shares it. Materials and nested referenced datablocks remain shared, matching
Blender datablock copy semantics. Duplicates link to the current scene's root
collection and receive a fresh UUID. Source UUID remains unchanged.
`created_ids` contains only the duplicate UUID. Source data is not edited.

## `object.set_parent`

Required: `object_id`. Optional: `parent_id`, `keep_world_transform` (default true).
Omitting `parent_id` clears the parent; null is not accepted.
Only object parenting is supported. Self-parenting and ancestry cycles return
`PARENT_CYCLE`. By default the current world pose is preserved using the new
parent's inverse matrix and the old world pose as local basis. A singular parent
matrix returns `INVALID_PARENT_TRANSFORM`; a sheared world pose that cannot be
represented in the new basis returns `UNSUPPORTED_OBJECT_STATE`. These checks
happen before changing the parent. Delta transforms are baked when preserving
world pose. With `keep_world_transform: false`, existing local components and
deltas stay intact and the parent inverse is reset to identity. The transform
restrictions above apply to the child. `modified_ids` contains the child UUID.

## `object.delete`

Required: `object_id`. Removes that object globally from Blender data, including
links in other scenes. Leaves mesh/material/other datablocks available; no orphan
purge runs. Direct children are unparented while preserving world poses. All direct
children must be editable and managed, satisfy the transform restrictions above,
and have representable world poses; otherwise the operation rejects before
changing any child or deleting the target. Descendants retain their relationships.
`deleted_ids` contains the target UUID; `modified_ids` contains direct child UUIDs
sorted lexically. References from other datablocks follow Blender unlink semantics;
this milestone does not report every indirect dependency change.

## Errors and limits

Alongside existing state, identity and schema errors: `OBJECT_READ_ONLY`,
`UNSUPPORTED_OBJECT_STATE`, `PARENT_CYCLE`, `INVALID_PARENT_TRANSFORM`,
`OBJECT_NOT_IN_SCENE`, `UNSUPPORTED_OBJECT_MODE`, `INVALID_ARGUMENT`.
Handler rejection advances the timeline even if preflight prevented scene changes.
Unexpected Blender exceptions are redacted as `INTERNAL_ERROR`. Creation and
copying clean up newly allocated data on failure. Other operations have no general
rollback guarantee; recovery is scheduled for Milestone 10.
