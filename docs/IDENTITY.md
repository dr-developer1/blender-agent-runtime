# Object identity

Managed objects store a canonical, nonzero UUID string in `obj["bar_uuid"]`.
Names are display labels. The Blender server initializes missing IDs on all
`bpy.data.objects` before publishing the session's revision-zero baseline. Existing
valid IDs are preserved. Pure Python API instances without an object provider do
not initialize identity or advertise `object_identity` support.

`runtime.identity.ObjectIdentity` takes a callable that returns the current object
collection. Blender uses `lambda: bpy.data.objects`, so file loads replace the
collection without invalidating the service. Every operation scans current data;
there is no persistent object-reference or pointer cache. Resolution includes
objects retained in Blender data even if they are unlinked from the scene. Removing
an object from Blender data makes its UUID unresolved. A new object with the same
name does not acquire the removed object's ID.

Internal helpers:

- `ensure_all()` validates existing identities and assigns missing IDs, returning
  the assigned UUIDs. Collision, malformed-ID and read-only checks precede writes.
- `ensure(obj)` manages one live object or returns its existing unique UUID.
- `resolve(object_id)` returns exactly one live object with that UUID.
- `assign_duplicate(source, duplicate)` replaces an inherited source UUID on a
  known new copy while preserving the source. Missing copy IDs are also assigned;
  copies already holding a distinct unique ID keep it.

A copied `bar_uuid` creates a collision until the known duplicate is assigned a
fresh ID. Unknown collisions are rejected; the resolver never picks an object by
name or collection order. The duplicate helper excludes only the caller's known
copy during validation; unrelated collisions still fail. It must run immediately
after duplication, before subsequent identity lookups. See Blender's
[ID copy API](https://docs.blender.org/api/current/bpy.types.ID.html#bpy.types.ID.copy)
for the underlying data-block operation.

After bootstrap, identity writes must run inside a mutation handler that declares
side effects, under the runtime's main-thread executor and revision guard. Identity
helpers do not advance revisions themselves, so the enclosing mutation advances
once. Future loading/restore handlers must preserve the runtime timeline and resolve
objects again by UUID. This milestone tests these hooks without introducing public
scene operations. Discovery remains read-only after initialization.

Errors: `INVALID_OBJECT_UUID`, `UUID_COLLISION`, `OBJECT_NOT_FOUND`,
`OBJECT_NOT_MANAGED`, `OBJECT_IDENTITY_READ_ONLY`, `OBJECT_IDENTITY_WRITE_FAILED`.
A malformed stored property is rejected rather than overwritten. Objects with
read-only data may be resolved if they already contain a valid unique ID; missing
IDs on such objects cannot be initialized. Linked-library management and automated
repair of arbitrary external edits are outside the current implementation.

Resolution currently performs a full scan and validates all managed IDs. Unexpected
write failures may leave a partially assigned batch. Identity helpers do not
create transactions; an explicit recovery checkpoint can restore saved contents
(see RECOVERY.md). Subsequent initialization preserves IDs already written. The
runtime records a mutation attempt's revision even if its handler fails.
