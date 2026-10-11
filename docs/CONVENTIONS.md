# Public conventions

- +Z is up; X/Y form the ground plane.
- Recommended asset forward is -Y and up is +Z.
- Public lengths may specify mm, cm or m; normalize internally to meters.
- Public angles use degrees; Blender conversion may use radians.
- Default Euler rotation order is XYZ.
- Dimensions mean evaluated world-space dimensions unless a tool says otherwise.

Future tools must document any deviation in their schemas/descriptions. Discovery
reports these conventions. Mesh selection lengths use meters in the chosen
coordinate space, areas use square meters and angles use degrees; see
SELECTION_LANGUAGE.md. No explicit unit conversion tools exist yet.
