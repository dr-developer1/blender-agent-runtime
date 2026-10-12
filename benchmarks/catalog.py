"""Versioned millimetre benchmark briefs and deliberately simple public-API recipes.

Role names are harness labels, never Blender object addresses. The evaluator uses
submitted UUIDs and independent overall dimension/assembly declarations.
"""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Part:
    role: str
    dimensions: tuple
    location: tuple
    primitive: str = 'CUBE'
    material: str = 'wood'
    # Through/open-top cavities: diameter/height or box XYZ, centered relative to part.
    cavity: tuple = ()
    cavity_offset: tuple = (0, 0, 0)
    # Box recesses: (XYZ dimensions, offset from part center), in millimetres.
    recesses: tuple = ()
    # Truncated cone: diameter at the upper end, with optional tapered bore.
    top_diameter: float = 0
    cavity_top_diameter: float = 0
    rotation: tuple = (0, 0, 0)
    # Additional vertical through-bores: (diameter, depth, relative center).
    holes: tuple = ()
    # Box apertures through Y-facing panels.
    openings: tuple = ()

    @property
    def world_dimensions(self):
        # Benchmark parts only use single-axis Euler rotations.
        import math
        x, y, z = self.dimensions
        rx, ry, rz = map(math.radians, self.rotation)
        if rx:
            y, z = abs(y*math.cos(rx))+abs(z*math.sin(rx)), abs(y*math.sin(rx))+abs(z*math.cos(rx))
        if ry:
            x, z = abs(x*math.cos(ry))+abs(z*math.sin(ry)), abs(x*math.sin(ry))+abs(z*math.cos(ry))
        if rz:
            x, y = abs(x*math.cos(rz))+abs(y*math.sin(rz)), abs(x*math.sin(rz))+abs(y*math.cos(rz))
        return (x, y, z)


@dataclass(frozen=True)
class Brief:
    name: str
    prompt: str
    dimensions: tuple
    parts: tuple
    grounds: tuple
    contacts: tuple = ()
    limitations: tuple = ()
    version: int = 1
    embedded: tuple = ()


def box(role, dimensions, location, material='wood'):
    return Part(role, dimensions, location, material=material)


def cylinder(role, diameter, height, z, material='metal', cavity=(), offset=(0, 0, 0)):
    return Part(role, (diameter, diameter, height), (0, 0, z), 'CYLINDER', material, cavity, offset)


def table(name, width, depth, height, material='wood'):
    parts = [box('top', (width, depth, 30), (0, 0, height-15), material)]
    for i, (x, y) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        parts.append(box(f'leg_{i+1}', (40, 40, height-30),
                         (x*(width/2-45), y*(depth/2-45), (height-30)/2), material))
    return Brief(name, f'Create a {width} × {depth} × {height} mm {name.replace("_", " ")} '
                 'with four straight legs, rounded edges and assigned materials.',
                 (width, depth, height), tuple(parts), tuple(p.role for p in parts[1:]),
                 tuple((p.role, 'top') for p in parts[1:]))


def tray(name, width, depth, height, material='wood'):
    t = 15
    parts = (box('base', (width, depth, t), (0, 0, t/2), material),
             box('left', (t, depth, height-t), (-(width-t)/2, 0, (height+t)/2), material),
             box('right', (t, depth, height-t), ((width-t)/2, 0, (height+t)/2), material),
             box('front', (width-2*t, t, height-t), (0, -(depth-t)/2, (height+t)/2), material),
             box('back', (width-2*t, t, height-t), (0, (depth-t)/2, (height+t)/2), material))
    return Brief(name, f'Create an open-top {width} × {depth} × {height} mm '
                 f'{name.replace("_", " ")} with a base and four walls, rounded edges and materials.',
                 (width, depth, height), parts, ('base',),
                 tuple(('base', p.role) for p in parts[1:]),
                 ('Separate closed wall meshes; corner joinery is not certified.',))


def shelves(name, width, depth, height, count):
    t = 20
    parts = [box('left', (t, depth, height), (-(width-t)/2, 0, height/2)),
             box('right', (t, depth, height), ((width-t)/2, 0, height/2))]
    for i in range(count):
        z = t/2 + i*(height-t)/(count-1)
        parts.append(box(f'shelf_{i+1}', (width-2*t, depth, t), (0, 0, z)))
    return Brief(name, f'Create a {width} × {depth} × {height} mm {name.replace("_", " ")} '
                 f'with two side panels and {count} shelves, rounded edges and wood material.',
                 (width, depth, height), tuple(parts), ('left', 'right', 'shelf_1'),
                 tuple((side, p.role) for side in ('left', 'right') for p in parts[2:]))


coffee = table('coffee_table', 1000, 600, 450)
crate = tray('storage_crate', 600, 400, 350)
wall = Brief('wall_shelf', 'Create an 800 × 250 × 200 mm wall shelf with two support brackets. '
             'Use rounded edges and wood/metal materials. Mounting strength is unverified.',
             (800, 250, 200),
             (box('shelf', (800, 250, 20), (0, 0, 190)),
              box('bracket_left', (25, 250, 180), (-300, 0, 90), 'metal'),
              box('bracket_right', (25, 250, 180), (300, 0, 90), 'metal')),
             (), (('bracket_left', 'shelf'), ('bracket_right', 'shelf')))
bottle = Brief('bottle', 'Create an opaque 90 mm diameter, 250 mm high bottle with a hollow '
               'body, tapered hollow shoulder, narrow open neck and PBR material.', (90, 90, 250),
               (cylinder('body', 90, 190, 95, 'plastic', (80, 80, 190), (0, 0, 5)),
                Part('shoulder', (90, 90, 20), (0, 0, 200), 'CONE', 'plastic',
                     (80, 80, 20), top_diameter=36, cavity_top_diameter=26),
                cylinder('neck', 36, 40, 230, 'plastic', (26, 26, 42))),
               ('body',), (('body', 'shoulder'), ('shoulder', 'neck')),
               ('Opacity only, no glass or liquid simulation.',), version=2)
book = shelves('bookshelf', 800, 300, 1600, 5)
base_cabinet = shelves('cabinet', 800, 450, 900, 3)
cabinet = Brief('cabinet', 'Create an 800 × 450 × 900 mm cabinet with two front doors, '
                'internal shelves and wood material.', (800, 450, 900),
                tuple(Part(p.role, (p.dimensions[0], 430, p.dimensions[2]),
                           (p.location[0], 10, p.location[2])) for p in base_cabinet.parts) +
                (box('door_left', (398, 20, 900), (-201, -215, 450)),
                 box('door_right', (398, 20, 900), (201, -215, 450))),
                ('left', 'right', 'shelf_1', 'door_left', 'door_right'),
                base_cabinet.contacts + (('left', 'door_left'), ('right', 'door_right')),
                ('Doors are static; hinges, swing clearance and back panel are not modeled.',))
lamp = Brief('desk_lamp', 'Create a 200 × 200 × 450 mm upright desk lamp with a circular '
              'base, stem and hollow cylindrical shade in metal material. '
              'The stem must reach the closed shade roof at Z=442 mm.', (200, 200, 450),
             (cylinder('base', 200, 20, 10), cylinder('stem', 20, 422, 231),
              cylinder('shade', 160, 120, 390, cavity=(144, 144, 120), offset=(0, 0, -8))),
             ('base',), (('base', 'stem'),),
             ('Diagnostic object only; no emissive light source or electrical certification.',), version=2)
scifi_base = tray('sci_fi_crate', 600, 400, 390, 'metal')
scifi = Brief('sci_fi_crate', 'Create a 600 × 400 × 400 mm closed sci-fi crate with a lid, '
              'two contrasting inset front plates and metal materials.', (600, 400, 400),
              tuple(replace(p, recesses=(((242, 9, 182), (-145, -4, 17.5)),
                                        ((242, 9, 182), (145, -4, 17.5))))
                    if p.role == 'front' else p for p in scifi_base.parts) +
              (box('lid', (600, 400, 10), (0, 0, 395), 'metal'),
                                  box('armor_left', (240, 8, 180), (-145, -196, 220), 'accent'),
                                  box('armor_right', (240, 8, 180), (145, -196, 220), 'accent')),
              ('base',), scifi_base.contacts + (('left', 'lid'), ('right', 'lid')),
              ('Front plates are decorative inlays, not structural armor.',), version=2)
bracket = Brief('metal_bracket', 'Create a 120 × 80 × 100 mm L bracket with a circular '
                'through-hole in its base and metallic material.', (120, 80, 100),
                (Part('base', (120, 80, 10), (0, 0, 5), material='metal', cavity=(20, 20, 12),
                      cavity_offset=(25, 0, 0)),
                 box('upright', (10, 80, 90), (-55, 0, 55), 'metal')),
                ('base',), (('base', 'upright'),), ('No fasteners, stress or load assessment.',))
pipe = Brief('pipe_connector', 'Create a hollow vertical pipe connector, 100 mm flange '
             'diameter and 150 mm high, with a 40 mm bore and metal material.', (100, 100, 150),
             (cylinder('tube', 60, 130, 65, cavity=(40, 40, 132)),
              cylinder('flange', 100, 20, 140, cavity=(40, 40, 22))),
             ('tube',), (('tube', 'flange'),), ('No thread, seals or pressure assessment.',))
drawer = tray('drawer', 500, 400, 180)
bench = table('bench', 1200, 400, 450)
chair_base = table('simple_chair', 450, 450, 450)
chair = Brief('simple_chair', 'Create a 450 × 450 × 850 mm chair with four legs, seat and '
              'a rear backrest, rounded edges and wood material.', (450, 450, 850),
              chair_base.parts + (box('backrest', (450, 30, 400), (0, 210, 650)),),
              chair_base.grounds, chair_base.contacts + (('top', 'backrest'),))
rack = shelves('shelving_unit', 1000, 400, 1800, 6)
planter = Brief('planter', 'Create a cylindrical open-top planter, 300 mm diameter and '
                '350 mm high, with a 15 mm wall and bottom and a matte material.', (300, 300, 350),
                (cylinder('pot', 300, 350, 175, 'ceramic', (270, 270, 350), (0, 0, 15)),),
                ('pot',), (), ('Drainage holes and horticultural suitability are unverified.',))
toolbase = tray('toolbox', 500, 250, 230, 'metal')
toolbox = Brief('toolbox', 'Create a 500 × 250 × 300 mm toolbox with an open tray and '
                'raised carry handle, rounded edges and metal/accent materials.', (500, 250, 300),
                toolbase.parts + (box('handle_left', (20, 20, 50), (-180, 0, 255), 'metal'),
                                   box('handle_right', (20, 20, 50), (180, 0, 255), 'metal'),
                                   box('handle', (380, 25, 20), (0, 0, 290), 'accent'),
                                   box('crossbar', (470, 20, 15), (0, 0, 222.5), 'metal')),
                ('base',), toolbase.contacts + (('left', 'crossbar'), ('right', 'crossbar'),
                                               ('crossbar', 'handle_left'), ('crossbar', 'handle_right'),
                                               ('handle_left', 'handle'), ('handle_right', 'handle')))
stand = Brief('monitor_stand', 'Create a 600 × 250 × 120 mm monitor stand with a top '
              'and two side supports, rounded edges and wood material.', (600, 250, 120),
              (box('top', (600, 250, 20), (0, 0, 110)),
               box('left', (30, 250, 100), (-270, 0, 50)),
               box('right', (30, 250, 100), (270, 0, 50))),
              ('left', 'right'), (('left', 'top'), ('right', 'top')))
side = table('side_table', 450, 450, 550)
appliance = Brief('appliance_housing', 'Create a 400 × 300 × 600 mm rectangular appliance '
                  'housing with an open front cavity, rounded edges and plastic material.',
                  (400, 300, 600),
                  (Part('housing', (400, 300, 600), (0, 0, 300), material='plastic',
                        cavity=(360, 300, 560), cavity_offset=(0, -20, 0)),),
                  ('housing',), (), ('No electronics, ventilation, UVs or manufacturing certification.',))
casing = Brief('product_casing', 'Create a 180 × 100 × 40 mm two-piece product casing '
               'with an interior cavity, contrasting lid and plastic materials.', (180, 100, 40),
               (Part('shell', (180, 100, 35), (0, 0, 17.5), material='plastic',
                     cavity=(170, 90, 35), cavity_offset=(0, 0, 5)),
                box('lid', (180, 100, 5), (0, 0, 37.5), 'accent')),
               ('shell',), (('shell', 'lid'),), ('No snap fits, fasteners or manufacturing tolerances.',))

CATALOG = {brief.name: brief for brief in (coffee, crate, wall, bottle, book, cabinet, lamp,
           scifi, bracket, pipe, drawer, bench, chair, rack, planter, toolbox, stand, side,
           appliance, casing)}
MATERIALS = {'wood': ([.22, .08, .025, 1], .65, 0),
             'metal': ([.24, .29, .34, 1], .35, .8),
             'plastic': ([.04, .12, .16, 1], .5, 0),
             'ceramic': ([.45, .22, .12, 1], .8, 0),
             'accent': ([.8, .22, .025, 1], .5, 0)}


# Version 3 replaces the original blockouts with visible construction details.
# Dimensions and functional omissions remain explicit; public tools build every part.
def detailed(brief, additions=(), contacts=(), replacements=None, limitations=None):
    replacements = replacements or {}
    parts = tuple(replacements.get(p.role, p) for p in brief.parts) + tuple(additions)
    return replace(brief, parts=parts, contacts=brief.contacts+tuple(contacts), version=3,
                   limitations=brief.limitations if limitations is None else tuple(limitations),
                   prompt=brief.prompt+' Include the declared supports, fittings and procedural surface finish.')


for name in ('coffee_table', 'bench', 'side_table', 'simple_chair'):
    b = CATALOG[name]
    width, depth, height = (b.dimensions if name != 'simple_chair' else (450, 450, 450))
    apron = [box('apron_front', (width-90, 20, 65), (0, -depth/2+45, height-62.5)),
             box('apron_back', (width-90, 20, 65), (0, depth/2-45, height-62.5)),
             box('apron_left', (20, depth-90, 65), (-width/2+45, 0, height-62.5)),
             box('apron_right', (20, depth-90, 65), (width/2-45, 0, height-62.5))]
    CATALOG[name] = detailed(b, apron, [(p.role, 'top') for p in apron])

# Chair rails tie the backrest to the seat and rear legs; lower stretchers brace legs.
b = CATALOG['simple_chair']
extras = [box('back_post_left', (25, 25, 420), (-175, 195, 640)),
          box('back_post_right', (25, 25, 420), (175, 195, 640)),
          box('stretcher_left', (20, 360, 25), (-180, 0, 180)),
          box('stretcher_right', (20, 360, 25), (180, 0, 180)),
          box('stretcher_front', (360, 20, 25), (0, -180, 180))]
CATALOG['simple_chair'] = detailed(b, extras, [('back_post_left','top'), ('back_post_right','top'),
    ('back_post_left','backrest'), ('back_post_right','backrest'),
    ('stretcher_left','leg_1'), ('stretcher_left','leg_2'),
    ('stretcher_right','leg_3'), ('stretcher_right','leg_4'), ('stretcher_front','leg_1')])

for name in ('bookshelf', 'shelving_unit', 'cabinet'):
    b = CATALOG[name]
    w,d,h = b.dimensions
    back = box('back_panel', (w-40, 8, h-40), (0, d/2-4, h/2))
    # Recess shelves ahead of the backing so solid meshes never occupy the same volume.
    repl = {p.role: replace(p, dimensions=(p.dimensions[0], p.dimensions[1]-8, p.dimensions[2]),
                            location=(p.location[0], p.location[1]-4, p.location[2]))
            for p in b.parts if p.role.startswith('shelf_')}
    CATALOG[name] = detailed(b, [back], [('back_panel','left'),('back_panel','right')], repl)

# Door fronts are inset to leave room for actual pulls inside the stated depth.
b = CATALOG['cabinet']
repl = {p.role: replace(p, dimensions=(p.dimensions[0], 20, 892), location=(p.location[0], -197, 450))
        for p in b.parts if p.role.startswith('door_')}
extras=[]; joints=[]
for side,x in (('left',-25),('right',25)):
    for i,z in enumerate((390,510)):
        extras.append(box(f'pull_{side}_mount_{i}', (12, 12, 12), (x,-213,z), 'metal'))
        joints.append((extras[-1].role, 'door_'+side))
    extras.append(box('pull_'+side, (12, 8, 132), (x,-221,450), 'metal'))
    joints.append(('pull_'+side,'pull_'+side+'_mount_0'))
b=replace(b, grounds=('left','right','shelf_1'))
CATALOG['cabinet'] = detailed(b, extras, joints, repl,
    ['Static inset doors and pulls; hinge motion and load ratings are unassessed.'])

# Recessed handholds and visible corner battens turn the open tray into a crate.
b=CATALOG['storage_crate']
repl={p.role: replace(p, openings=(((150,25,35),(0,0,105)),))
      for p in b.parts if p.role in ('front','back')}
extras=[]
for i,(x,y) in enumerate(((-270,-165),(-270,165),(270,-165),(270,165))):
    extras.append(box('corner_batten_'+str(i+1),(30,30,335),(x,y,182.5)))
CATALOG['storage_crate']=detailed(b,extras,[(p.role,'base') for p in extras],repl)

# Wall shelf: real rear mounting plates, horizontal arms and diagonal gussets.
b=CATALOG['wall_shelf']; repl={}; extras=[]; joints=[]
for side,x in (('left',-300),('right',300)):
    role='bracket_'+side
    repl[role]=box(role,(25,16,180),(x,117,90),'metal')
    arm=box('arm_'+side,(25,234,12),(x,-8,174),'metal')
    diagonal=Part('brace_'+side,(16,12,250),(x,12,96),material='metal',rotation=(51,0,0))
    extras.extend((arm,diagonal))
    joints.extend(((role,arm.role),(diagonal.role,role),(diagonal.role,arm.role),(arm.role,'shelf')))
CATALOG['wall_shelf']=detailed(b,extras,joints,repl)

# Shallow mechanical fittings; all stay inside the overall benchmark envelope.
b=CATALOG['sci_fi_crate']; extras=[]; joints=[]
for side,x in (('left',-230),('right',230)):
    extras.append(box('latch_'+side,(35,10,60),(x,-195,360),'accent'))
    joints.extend(((extras[-1].role,'front'),(extras[-1].role,'lid')))
for side,x in (('left',-270),('right',270)):
    extras.append(box('corner_rail_'+side,(20,10,350),(x,-195,185),'accent'))
    joints.append((extras[-1].role,'base'))
front=next(p for p in b.parts if p.role=='front')
pockets=tuple(((37,12,62),(x,-2.5,157.5)) for x in (-230,230)) + tuple(((22,12,352),(x,-2.5,-17.5)) for x in (-270,270))
CATALOG['sci_fi_crate']=detailed(b,extras,joints,{'front':replace(front,recesses=front.recesses+pockets)})

b=CATALOG['metal_bracket']
CATALOG['metal_bracket']=detailed(b,replacements={'base':replace(b.parts[0],
    holes=((12,12,(-25,-22,0)),(12,12,(-25,22,0))))})
b=CATALOG['pipe_connector']
CATALOG['pipe_connector']=detailed(b,replacements={'flange':replace(b.parts[1],
    holes=tuple((10,22,(x,y,0)) for x,y in ((-29,-29),(-29,29),(29,-29),(29,29))))})

b=CATALOG['drawer']
# Front is set back 16 mm for a pull that sits within the original 400 mm depth.
repl={'front':replace(next(p for p in b.parts if p.role=='front'),location=(0,-176.5,97.5))}
extras=[box('pull_left',(12,12,12),(-70,-188,95),'metal'),
        box('pull_right',(12,12,12),(70,-188,95),'metal'),
        box('pull',(152,6,14),(0,-197,95),'metal')]
CATALOG['drawer']=detailed(b,extras,[('pull_left','front'),('pull_right','front'),
    ('pull','pull_left'),('pull','pull_right')],repl)

b=CATALOG['desk_lamp']
extras=[cylinder('stem_collar',36,12,26,'accent'),
        cylinder('socket',38,25,423.5,'accent'),
        Part('switch',(14,14,5),(55,0,17.5),'CYLINDER','accent')]
CATALOG['desk_lamp']=detailed(b,extras,[('base','stem_collar'),('stem','socket'),('base','switch')])

b=CATALOG['bottle']
# Slightly proud molded neck bead gives a readable closure seat without changing overall bounds.
extras=[cylinder('neck_bead',40,5,240,'accent',cavity=(26,26,7))]
CATALOG['bottle']=detailed(b,extras,[('neck','neck_bead')])

b=CATALOG['planter']
CATALOG['planter']=detailed(b,replacements={'pot':replace(b.parts[0],holes=((12,20,(0,0,-168)),))},
    limitations=['Drainage bore modeled; horticultural suitability and firing shrinkage unassessed.'])

b=CATALOG['toolbox']
extras=[box('corner_left',(18,18,205),(-229,-107,117.5),'accent'),
        box('corner_right',(18,18,205),(229,-107,117.5),'accent')]
CATALOG['toolbox']=detailed(b,extras,[(p.role,'base') for p in extras])
b=CATALOG['monitor_stand']
extras=[box('rear_rail',(510,20,40),(0,110,80))]
CATALOG['monitor_stand']=detailed(b,extras,[('rear_rail','top'),('rear_rail','left'),('rear_rail','right')])

b=CATALOG['appliance_housing']; p=b.parts[0]
vents=tuple(((12,40,80),(x,140,-180)) for x in (-120,-80,-40,0,40,80,120))
CATALOG['appliance_housing']=detailed(b,replacements={'housing':replace(p,openings=vents)},
    limitations=['Rear ventilation slots modeled; no electronics or manufacturing certification.'])

b=CATALOG['product_casing']
extras=[]; joints=[]
for i,(x,y) in enumerate(((-81,-41),(-81,41),(81,-41),(81,41))):
    # Bosses overlap the shell wall; heads end flush with the lid top.
    extras.append(Part('boss_'+str(i),(12,12,28),(x,y,18),'CYLINDER','plastic',holes=((4,30,(0,0,0)),)))
    extras.append(Part('screw_'+str(i),(7,7,2),(x,y,39),'CYLINDER','metal'))
    joints.extend(((extras[-2].role,'shell'),(extras[-1].role,'lid')))
lid=next(p for p in b.parts if p.role=='lid')
CATALOG['product_casing']=detailed(b,extras,joints,{'lid':replace(lid,holes=tuple(
    (7.4,6,(x,y,1.5)) for x,y in ((-81,-41),(-81,41),(81,-41),(81,41))))})

SURFACES = {'wood':'wood', 'metal':'coated_metal', 'plastic':'polymer',
            'ceramic':'ceramic', 'accent':'polymer'}
# Warm oiled oak, satin graphite, deep blue molded polymer, terracotta, burnt orange.
MATERIALS.update(wood=([.32,.18,.075,1],.42,0), metal=([.11,.14,.17,1],.3,.72),
                 plastic=([.025,.085,.12,1],.28,0), ceramic=([.40,.16,.075,1],.7,0),
                 accent=([.55,.12,.025,1],.36,0))


def material_key(part):
    axis = 'XYZ'[max(range(3), key=lambda i: part.dimensions[i])]
    return (part.material, axis if part.material == 'wood' else None)


def material_arguments(part, *, agent=False):
    color, roughness, metallic = MATERIALS[part.material]
    args={'name':('Codex ' if agent else '')+part.material,
          'base_color':list(color), 'roughness':roughness, 'metallic':metallic,
          'surface':SURFACES[part.material]}
    if part.material=='wood':
        args['grain_axis']=material_key(part)[1]
    if agent:
        args['roughness']=min(1,roughness+.025)
        args['base_color']=[min(1,c*1.04) for c in color[:3]]+[1]
    return args


# The legacy contact check rejects deep AABB overlap. Sleeves, inset screws,
# gussets and housed joinery intentionally overlap; record them separately.
for name, brief in tuple(CATALOG.items()):
    parts = {p.role:p for p in brief.parts}
    contacts, embedded = [], []
    for a,b in brief.contacts:
        pa,pb=parts[a],parts[b]
        overlaps=[min(ca+da/2,cb+db/2)-max(ca-da/2,cb-db/2)
                  for ca,da,cb,db in zip(pa.location,pa.world_dimensions,pb.location,pb.world_dimensions)]
        (embedded if min(overlaps)>=1.99 else contacts).append((a,b))
    CATALOG[name]=replace(brief,contacts=tuple(contacts),embedded=tuple(embedded))
