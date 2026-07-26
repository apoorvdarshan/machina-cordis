"""Build the MACHINA CORDIS mechanical heart reactor scene in Blender."""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
BLEND_PATH = ROOT / "MACHINA-CORDIS.blend"
OUTPUT_DIR = ROOT / "output"
PREVIEW_PATH = OUTPUT_DIR / "machina-cordis-preview.png"


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for existing_collection in list(bpy.data.collections):
        bpy.data.collections.remove(existing_collection)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def collection(name: str) -> bpy.types.Collection:
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    return result


def move_to_collection(obj: bpy.types.Object, target: bpy.types.Collection) -> None:
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    target.objects.link(obj)


def set_input(node: bpy.types.Node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.4,
    transmission: float = 0.0,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
    brushed: bool = False,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    set_input(bsdf, "Base Color", color)
    set_input(bsdf, "Metallic", metallic)
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Transmission Weight", transmission)
    set_input(bsdf, "Alpha", alpha)
    if emission is not None:
        set_input(bsdf, "Emission Color", emission)
        set_input(bsdf, "Emission Strength", emission_strength)
    if alpha < 1.0:
        mat.diffuse_color = (*color[:3], alpha)
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "DITHERED"
    if brushed:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.name = f"{name} micro-scratches"
        noise.inputs["Scale"].default_value = 135.0
        noise.inputs["Detail"].default_value = 2.0
        noise.inputs["Roughness"].default_value = 0.68
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (0.2, 7.0, 1.1)
        texcoord = nodes.new("ShaderNodeTexCoord")
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.16
        bump.inputs["Distance"].default_value = 0.025
        links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def apply_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)


def smooth(obj: bpy.types.Object) -> None:
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def rounded_box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    bevel: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    modifier = obj.modifiers.new("Precision edge radius", "BEVEL")
    modifier.width = bevel
    modifier.segments = 4
    apply_material(obj, mat)
    move_to_collection(obj, target)
    return obj


def uv_sphere(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    segments: int = 48,
    rings: int = 24,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    smooth(obj)
    apply_material(obj, mat)
    move_to_collection(obj, target)
    return obj


def cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    vertices: int = 40,
    bevel: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    smooth(obj)
    if bevel:
        modifier = obj.modifiers.new("Machined edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
    apply_material(obj, mat)
    move_to_collection(obj, target)
    return obj


def cylinder_between(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    vertices: int = 32,
) -> bpy.types.Object:
    a = Vector(start)
    b = Vector(end)
    direction = b - a
    midpoint = (a + b) * 0.5
    obj = cylinder(
        name,
        midpoint,
        radius,
        direction.length,
        mat,
        target,
        vertices=vertices,
        bevel=min(radius * 0.2, 0.025),
    )
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    return obj


def torus(
    name: str,
    location: tuple[float, float, float],
    major_radius: float,
    minor_radius: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=64,
        minor_segments=12,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    smooth(obj)
    apply_material(obj, mat)
    move_to_collection(obj, target)
    return obj


def curve_tube(
    name: str,
    points: list[tuple[float, float, float]],
    radius: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    resolution: int = 3,
) -> bpy.types.Object:
    curve_data = bpy.data.curves.new(name, "CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 12
    curve_data.bevel_depth = radius
    curve_data.bevel_resolution = resolution
    curve_data.resolution_u = 16
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bezier, point in zip(spline.bezier_points, points):
        bezier.co = point
        bezier.handle_left_type = "AUTO"
        bezier.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve_data)
    target.objects.link(obj)
    apply_material(obj, mat)
    return obj


def text_object(
    name: str,
    body: str,
    location: tuple[float, float, float],
    size: float,
    mat: bpy.types.Material,
    target: bpy.types.Collection,
    rotation: tuple[float, float, float] = (math.radians(90), 0.0, 0.0),
    extrude: float = 0.006,
) -> bpy.types.Object:
    data = bpy.data.curves.new(name, "FONT")
    data.body = body
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.extrude = extrude
    data.bevel_depth = 0.0015
    data.bevel_resolution = 2
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    obj.rotation_euler = rotation
    target.objects.link(obj)
    apply_material(obj, mat)
    return obj


def look_at(obj: bpy.types.Object, point: tuple[float, float, float]) -> None:
    direction = Vector(point) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def keyframe_socket(socket: bpy.types.NodeSocket, values: list[tuple[int, float]]) -> None:
    for frame, value in values:
        socket.default_value = value
        socket.keyframe_insert("default_value", frame=frame)


def build() -> None:
    clear_scene()
    OUTPUT_DIR.mkdir(exist_ok=True)

    pedestal = collection("01 — Reactor pedestal")
    core = collection("02 — Heart core")
    vascular = collection("03 — Vascular system")
    mechanisms = collection("04 — Pulse mechanisms")
    frame = collection("05 — Support frame")
    labels = collection("06 — Markings")
    lighting = collection("07 — Lighting")

    titanium = material(
        "Brushed surgical titanium",
        (0.25, 0.28, 0.31, 1.0),
        metallic=0.92,
        roughness=0.36,
        brushed=True,
    )
    dark_titanium = material(
        "Dark machined titanium",
        (0.055, 0.065, 0.075, 1.0),
        metallic=0.88,
        roughness=0.34,
        brushed=True,
    )
    ceramic = material(
        "Medical black ceramic",
        (0.012, 0.016, 0.022, 1.0),
        metallic=0.18,
        roughness=0.2,
    )
    brass = material(
        "Aged brass fittings",
        (0.38, 0.19, 0.055, 1.0),
        metallic=0.9,
        roughness=0.29,
        brushed=True,
    )
    rubber = material(
        "Matte surgical rubber",
        (0.015, 0.018, 0.022, 1.0),
        roughness=0.72,
    )
    arterial = material(
        "Arterial fluid",
        (0.17, 0.005, 0.008, 1.0),
        metallic=0.05,
        roughness=0.34,
        emission=(0.42, 0.003, 0.004, 1.0),
        emission_strength=0.55,
    )
    venous = material(
        "Venous fluid",
        (0.008, 0.035, 0.16, 1.0),
        metallic=0.05,
        roughness=0.34,
        emission=(0.004, 0.05, 0.42, 1.0),
        emission_strength=0.5,
    )
    amber = material(
        "Amber indicator",
        (0.25, 0.07, 0.005, 1.0),
        roughness=0.24,
        emission=(1.0, 0.13, 0.008, 1.0),
        emission_strength=5.0,
    )
    pale_green = material(
        "Stable status indicator",
        (0.006, 0.18, 0.06, 1.0),
        roughness=0.2,
        emission=(0.02, 0.9, 0.16, 1.0),
        emission_strength=4.0,
    )
    glass = material(
        "Laboratory borosilicate glass",
        (0.3, 0.42, 0.48, 1.0),
        roughness=0.08,
        transmission=0.92,
        alpha=0.34,
    )
    white = material(
        "Instrument markings",
        (0.78, 0.82, 0.84, 1.0),
        metallic=0.05,
        roughness=0.32,
    )
    warning = material(
        "Safety ochre",
        (0.82, 0.29, 0.025, 1.0),
        metallic=0.15,
        roughness=0.35,
    )

    # Pedestal and controls.
    rounded_box(
        "Isolation plinth",
        (0.0, 0.0, 0.18),
        (4.2, 3.35, 0.36),
        0.17,
        dark_titanium,
        pedestal,
    )
    rounded_box(
        "Reactor bed",
        (0.0, 0.0, 0.45),
        (3.65, 2.82, 0.26),
        0.13,
        titanium,
        pedestal,
    )
    rounded_box(
        "Ceramic inset",
        (0.0, 0.0, 0.61),
        (3.18, 2.38, 0.09),
        0.09,
        ceramic,
        pedestal,
    )
    torus("Bed trim", (0.0, 0.0, 0.68), 1.28, 0.035, brass, pedestal, scale=(1.12, 0.82, 1.0))

    for index in range(12):
        angle = math.tau * index / 12.0
        x = 1.72 * math.cos(angle)
        y = 1.30 * math.sin(angle)
        cylinder(
            f"Bed fastener {index + 1:02d}",
            (x, y, 0.68),
            0.055,
            0.055,
            brass,
            pedestal,
            bevel=0.008,
        )

    gauge_rim = cylinder(
        "Pressure gauge rim",
        (-1.18, -1.57, 0.69),
        0.31,
        0.15,
        brass,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
        bevel=0.025,
    )
    cylinder(
        "Pressure gauge face",
        (-1.18, -1.66, 0.69),
        0.255,
        0.025,
        ceramic,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
    )
    gauge_needle = rounded_box(
        "Pressure gauge needle",
        (-1.18, -1.69, 0.69),
        (0.025, 0.018, 0.21),
        0.008,
        warning,
        mechanisms,
        rotation=(0.0, 0.0, math.radians(-28)),
    )
    gauge_needle.rotation_mode = "XYZ"
    for frame_number, angle in ((1, -28), (30, -28), (48, 18), (60, 5), (84, 21), (96, 6), (120, 20), (144, 5)):
        gauge_needle.rotation_euler.y = math.radians(angle)
        gauge_needle.keyframe_insert("rotation_euler", frame=frame_number, index=1)

    cylinder(
        "Stable status lamp bezel",
        (1.24, -1.61, 0.72),
        0.16,
        0.12,
        titanium,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
        bevel=0.018,
    )
    status_lamp = cylinder(
        "Stable status lamp",
        (1.24, -1.69, 0.72),
        0.105,
        0.02,
        pale_green,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
    )

    # Anatomically inspired mechanical chambers.
    left_ventricle = uv_sphere(
        "Left titanium ventricle",
        (-0.38, 0.0, 2.08),
        (0.79, 0.62, 1.18),
        titanium,
        core,
        rotation=(0.0, math.radians(-8), math.radians(8)),
    )
    right_ventricle = uv_sphere(
        "Right titanium ventricle",
        (0.48, 0.04, 2.23),
        (0.71, 0.59, 1.04),
        dark_titanium,
        core,
        rotation=(0.0, math.radians(9), math.radians(-11)),
    )
    uv_sphere(
        "Left atrial actuator",
        (-0.46, 0.02, 3.12),
        (0.57, 0.5, 0.56),
        dark_titanium,
        core,
        rotation=(0.0, math.radians(-10), math.radians(7)),
    )
    uv_sphere(
        "Right atrial actuator",
        (0.52, 0.07, 3.12),
        (0.52, 0.47, 0.5),
        titanium,
        core,
        rotation=(0.0, math.radians(8), math.radians(-8)),
    )
    uv_sphere(
        "Reactor apex",
        (-0.03, 0.02, 1.22),
        (0.53, 0.45, 0.65),
        ceramic,
        core,
    )
    cylinder(
        "Central septum spine",
        (0.03, 0.18, 2.35),
        0.13,
        2.44,
        brass,
        core,
        bevel=0.02,
    )

    for chamber_name, x, z, scale_x, scale_y in (
        ("Left", -0.38, 2.08, 1.0, 0.82),
        ("Right", 0.48, 2.23, 0.88, 0.77),
    ):
        for band_index, offset in enumerate((-0.48, 0.0, 0.48)):
            torus(
                f"{chamber_name} compression band {band_index + 1}",
                (x, 0.0, z + offset),
                0.61,
                0.028,
                brass if band_index == 1 else dark_titanium,
                core,
                scale=(scale_x, scale_y, 1.0),
            )

    # Front inspection ports, diaphragms, and fasteners.
    for side_name, x, z, fluid_mat in (
        ("Arterial", -0.39, 2.18, arterial),
        ("Venous", 0.49, 2.30, venous),
    ):
        cylinder(
            f"{side_name} inspection bezel",
            (x, -0.61, z),
            0.38,
            0.13,
            brass,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
            bevel=0.025,
        )
        cylinder(
            f"{side_name} inspection glass",
            (x, -0.69, z),
            0.315,
            0.028,
            glass,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
        )
        diaphragm = cylinder(
            f"{side_name} pulse diaphragm",
            (x, -0.72, z),
            0.235,
            0.024,
            fluid_mat,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
        )
        diaphragm["pulse_component"] = True
        for bolt_index in range(8):
            angle = math.tau * bolt_index / 8.0
            cylinder(
                f"{side_name} port fastener {bolt_index + 1}",
                (x + 0.33 * math.cos(angle), -0.695, z + 0.33 * math.sin(angle)),
                0.022,
                0.035,
                titanium,
                mechanisms,
                rotation=(math.radians(90), 0.0, 0.0),
                vertices=20,
            )

    # Glass vascular lines with emissive fluid cores.
    aorta_points = [
        (-0.48, 0.05, 3.38),
        (-0.68, 0.03, 3.82),
        (-0.36, 0.08, 4.22),
        (0.22, 0.12, 4.38),
        (0.86, 0.08, 4.08),
        (1.02, 0.04, 3.60),
    ]
    curve_tube("Aorta glass conduit", aorta_points, 0.155, glass, vascular, resolution=5)
    aorta_fluid = curve_tube("Aorta arterial flow", aorta_points, 0.074, arterial, vascular, resolution=4)
    pulmonary_points = [
        (0.50, -0.08, 3.30),
        (0.86, -0.26, 3.52),
        (1.12, -0.40, 3.30),
        (0.72, -0.55, 3.05),
        (0.02, -0.48, 3.04),
    ]
    curve_tube("Pulmonary glass conduit", pulmonary_points, 0.13, glass, vascular, resolution=5)
    pulmonary_fluid = curve_tube("Pulmonary venous flow", pulmonary_points, 0.058, venous, vascular, resolution=4)

    for index, point in enumerate((aorta_points[0], aorta_points[-1])):
        torus(
            f"Aorta coupling {index + 1}",
            point,
            0.16,
            0.038,
            brass,
            vascular,
        )
    for index, point in enumerate((pulmonary_points[0], pulmonary_points[-1])):
        torus(
            f"Pulmonary coupling {index + 1}",
            point,
            0.135,
            0.032,
            brass,
            vascular,
        )

    for name, x, flow_mat, points in (
        (
            "Arterial return",
            -0.78,
            arterial,
            [(-0.70, -0.02, 1.72), (-1.10, -0.25, 1.45), (-1.35, -0.30, 0.80)],
        ),
        (
            "Venous return",
            0.82,
            venous,
            [(0.74, 0.0, 1.78), (1.15, -0.22, 1.42), (1.42, -0.28, 0.80)],
        ),
    ):
        curve_tube(f"{name} glass", points, 0.115, glass, vascular, resolution=4)
        curve_tube(f"{name} fluid", points, 0.050, flow_mat, vascular, resolution=3)
        torus(
            f"{name} lower coupling",
            (points[-1][0], points[-1][1], points[-1][2]),
            0.115,
            0.035,
            brass,
            vascular,
        )

    # Synchronized linear pulse actuators.
    pistons: list[bpy.types.Object] = []
    for side, sign in (("Left", -1), ("Right", 1)):
        for level_index, z in enumerate((1.78, 2.62)):
            cylinder_between(
                f"{side} actuator housing {level_index + 1}",
                (sign * 1.18, 0.06, z),
                (sign * 1.72, 0.06, z),
                0.17,
                dark_titanium,
                mechanisms,
            )
            piston = cylinder_between(
                f"{side} actuator piston {level_index + 1}",
                (sign * 0.70, 0.06, z),
                (sign * 1.28, 0.06, z),
                0.065,
                brass,
                mechanisms,
            )
            piston["pulse_component"] = True
            pistons.append(piston)
            torus(
                f"{side} actuator seal {level_index + 1}",
                (sign * 1.18, 0.06, z),
                0.17,
                0.025,
                rubber,
                mechanisms,
                rotation=(0.0, math.radians(90), 0.0),
            )

    # Side-mounted timing gear and teeth.
    gear_center = Vector((1.52, 0.48, 2.42))
    torus(
        "Pulse timing gear",
        gear_center,
        0.54,
        0.085,
        brass,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
    )
    timing_teeth: list[bpy.types.Object] = []
    for index in range(20):
        angle = math.tau * index / 20
        tooth = rounded_box(
            f"Timing tooth {index + 1:02d}",
            (
                gear_center.x + 0.66 * math.cos(angle),
                gear_center.y,
                gear_center.z + 0.66 * math.sin(angle),
            ),
            (0.13, 0.15, 0.07),
            0.018,
            brass,
            mechanisms,
            rotation=(0.0, -angle, 0.0),
        )
        timing_teeth.append(tooth)
    cylinder(
        "Timing gear axle",
        (gear_center.x, gear_center.y - 0.08, gear_center.z),
        0.19,
        0.30,
        titanium,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
        bevel=0.025,
    )
    cylinder(
        "Timing gear pulse cap",
        (gear_center.x, gear_center.y - 0.25, gear_center.z),
        0.12,
        0.025,
        arterial,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
    )
    cylinder_between(
        "Timing transmission shaft",
        (0.66, gear_center.y, gear_center.z),
        (gear_center.x, gear_center.y, gear_center.z),
        0.055,
        brass,
        mechanisms,
    )

    # Structural frame kept behind the organ to preserve a clear silhouette.
    for sign in (-1, 1):
        cylinder_between(
            f"Rear frame pillar {'L' if sign < 0 else 'R'}",
            (sign * 1.48, 0.72, 0.68),
            (sign * 1.48, 0.72, 4.15),
            0.095,
            titanium,
            frame,
        )
        cylinder_between(
            f"Lower diagonal brace {'L' if sign < 0 else 'R'}",
            (sign * 1.48, 0.72, 1.12),
            (sign * 0.86, 0.44, 1.60),
            0.06,
            dark_titanium,
            frame,
        )
    cylinder_between("Upper frame bridge", (-1.48, 0.72, 4.15), (1.48, 0.72, 4.15), 0.095, titanium, frame)
    torus(
        "Upper stabilization halo",
        (0.0, 0.08, 4.13),
        1.18,
        0.045,
        brass,
        frame,
        scale=(1.0, 0.73, 1.0),
    )
    for sign in (-1, 1):
        curve_tube(
            f"Monitor cable {'L' if sign < 0 else 'R'}",
            [
                (sign * 1.43, 0.69, 3.75),
                (sign * 1.18, 0.72, 3.25),
                (sign * 0.84, 0.62, 2.86),
            ],
            0.035,
            rubber,
            frame,
            resolution=3,
        )

    # Precision markings and nameplate.
    rounded_box(
        "Front nameplate",
        (0.0, -1.70, 0.34),
        (1.92, 0.055, 0.40),
        0.035,
        ceramic,
        labels,
    )
    text_object(
        "MACHINA CORDIS name",
        "MACHINA CORDIS",
        (0.0, -1.738, 0.41),
        0.205,
        warning,
        labels,
    )
    text_object(
        "Reactor subtitle",
        "MECHANICAL HEART REACTOR",
        (0.0, -1.741, 0.235),
        0.068,
        white,
        labels,
    )
    text_object(
        "Status legend",
        "PULSE STABLE",
        (1.48, -1.747, 0.43),
        0.058,
        pale_green,
        labels,
    )
    text_object(
        "Serial number",
        "MC-V7 / SURGICAL CORE",
        (-1.42, -1.742, 0.24),
        0.047,
        white,
        labels,
    )

    for index in range(8):
        x = -0.52 + index * 0.15
        rounded_box(
            f"Warning stripe {index + 1}",
            (x, -1.705, 0.72),
            (0.085, 0.032, 0.12),
            0.008,
            warning if index % 2 == 0 else ceramic,
            labels,
            rotation=(0.0, math.radians(18), 0.0),
        )

    # Pulse animation: two asymmetric ventricular beats per loop.
    pulse_frames = (1, 36, 72, 108, 144)
    for chamber, intensity in ((left_ventricle, 1.0), (right_ventricle, 0.72)):
        base_scale = chamber.scale.copy()
        for start in pulse_frames[:-1]:
            for offset, factor in ((0, 1.0), (8, 1.0 + 0.055 * intensity), (14, 0.985), (24, 1.0)):
                chamber.scale = base_scale * factor
                chamber.keyframe_insert("scale", frame=start + offset)

    for piston in pistons:
        base_location = piston.location.copy()
        direction = 1 if base_location.x < 0 else -1
        for start in pulse_frames[:-1]:
            for offset, displacement in ((0, 0.0), (8, 0.10), (14, -0.025), (24, 0.0)):
                piston.location = base_location + Vector((direction * displacement, 0.0, 0.0))
                piston.keyframe_insert("location", frame=start + offset)

    for animated_mat, strength_values in (
        (arterial, [(1, 0.2), (9, 1.35), (18, 0.4), (37, 0.2), (45, 1.35), (54, 0.4), (73, 0.2), (81, 1.35), (90, 0.4), (109, 0.2), (117, 1.35), (126, 0.4), (144, 0.2)]),
        (venous, [(1, 0.18), (12, 1.15), (22, 0.35), (37, 0.18), (48, 1.15), (58, 0.35), (73, 0.18), (84, 1.15), (94, 0.35), (109, 0.18), (120, 1.15), (130, 0.35), (144, 0.18)]),
    ):
        animated_bsdf = animated_mat.node_tree.nodes.get("Principled BSDF")
        emission_socket = animated_bsdf.inputs.get("Emission Strength")
        if emission_socket:
            keyframe_socket(emission_socket, strength_values)

    stable_bsdf = pale_green.node_tree.nodes.get("Principled BSDF")
    stable_socket = stable_bsdf.inputs.get("Emission Strength")
    if stable_socket:
        keyframe_socket(stable_socket, [(1, 0.1), (26, 0.1), (40, 4.0), (144, 4.0)])

    # Floor and cinematic lighting.
    floor = rounded_box(
        "Laboratory floor",
        (0.0, 0.0, -0.16),
        (12.0, 12.0, 0.24),
        0.05,
        ceramic,
        lighting,
    )

    def area_light(
        name: str,
        location: tuple[float, float, float],
        energy: float,
        color: tuple[float, float, float],
        size: float,
        target_point: tuple[float, float, float],
    ) -> bpy.types.Object:
        light_data = bpy.data.lights.new(name, "AREA")
        light_data.energy = energy
        light_data.color = color
        light_data.shape = "DISK"
        light_data.size = size
        light_obj = bpy.data.objects.new(name, light_data)
        light_obj.location = location
        lighting.objects.link(light_obj)
        look_at(light_obj, target_point)
        return light_obj

    area_light("Cold surgical key", (4.5, -5.0, 6.8), 780.0, (0.72, 0.86, 1.0), 4.0, (0.0, 0.0, 2.2))
    area_light("Warm mechanical rim", (-4.0, 1.4, 5.2), 620.0, (1.0, 0.38, 0.12), 3.0, (0.0, 0.2, 2.6))
    area_light("Soft overhead", (0.0, 0.5, 8.0), 580.0, (0.88, 0.93, 1.0), 3.5, (0.0, 0.0, 2.0))
    area_light("Front fill", (0.0, -5.0, 2.4), 300.0, (0.32, 0.5, 0.8), 3.0, (0.0, 0.0, 2.0))

    camera_data = bpy.data.cameras.new("MACHINA CORDIS camera")
    camera = bpy.data.objects.new("MACHINA CORDIS camera", camera_data)
    camera.location = (7.0, -8.2, 5.6)
    camera_data.lens = 58
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.focus_object = left_ventricle
    camera_data.dof.aperture_fstop = 6.3
    lighting.objects.link(camera)
    look_at(camera, (0.0, 0.0, 2.15))

    scene = bpy.context.scene
    scene.camera = camera
    scene.frame_start = 1
    scene.frame_end = 144
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PREVIEW_PATH)
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.resolution_percentage = 100
    scene.render.use_file_extension = True
    if hasattr(scene, "eevee"):
        scene.eevee.taa_samples = 48
    scene.world.color = (0.004, 0.006, 0.01)
    if scene.world.use_nodes:
        background = scene.world.node_tree.nodes.get("Background")
        background.inputs["Color"].default_value = (0.004, 0.007, 0.014, 1.0)
        background.inputs["Strength"].default_value = 0.16

    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = str(PREVIEW_PATH)
    scene["project"] = "MACHINA CORDIS"
    scene["description"] = "Animated mechanical heart reactor"
    scene["playback"] = "Frames 1–144 at 24 fps"
    scene["render_engine"] = "Eevee Next"
    scene["safe_build"] = "Moderate geometry, no simulations, no external textures"

    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    scene.frame_set(48)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), check_existing=False)
    bpy.ops.render.render(write_still=True)
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), check_existing=False)

    animated_objects = sum(1 for obj in scene.objects if obj.animation_data)
    print(
        "MACHINA CORDIS build complete:",
        f"{len(scene.objects)} objects,",
        f"{animated_objects} animated objects,",
        f"blend={BLEND_PATH},",
        f"preview={PREVIEW_PATH}",
    )


if __name__ == "__main__":
    build()
