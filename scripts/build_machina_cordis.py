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
        roughness_ramp = nodes.new("ShaderNodeValToRGB")
        roughness_ramp.name = f"{name} roughness variation"
        low_roughness = max(0.04, roughness * 0.72)
        high_roughness = min(0.92, roughness * 1.38)
        roughness_ramp.color_ramp.elements[0].color = (
            low_roughness,
            low_roughness,
            low_roughness,
            1.0,
        )
        roughness_ramp.color_ramp.elements[1].color = (
            high_roughness,
            high_roughness,
            high_roughness,
            1.0,
        )
        links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(noise.outputs["Fac"], roughness_ramp.inputs["Fac"])
        links.new(roughness_ramp.outputs["Color"], bsdf.inputs["Roughness"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        broad_noise = nodes.new("ShaderNodeTexNoise")
        broad_noise.name = f"{name} broad oxidation"
        broad_noise.inputs["Scale"].default_value = 3.4
        broad_noise.inputs["Detail"].default_value = 4.5
        broad_noise.inputs["Roughness"].default_value = 0.62
        color_ramp = nodes.new("ShaderNodeValToRGB")
        color_ramp.name = f"{name} color variation"
        dark_color = tuple(max(0.002, channel * 0.76) for channel in color[:3])
        bright_color = tuple(min(1.0, channel * 1.14 + 0.008) for channel in color[:3])
        color_ramp.color_ramp.elements[0].position = 0.26
        color_ramp.color_ramp.elements[0].color = (*dark_color, 1.0)
        color_ramp.color_ramp.elements[1].position = 0.74
        color_ramp.color_ramp.elements[1].color = (*bright_color, 1.0)
        links.new(texcoord.outputs["Generated"], broad_noise.inputs["Vector"])
        links.new(broad_noise.outputs["Fac"], color_ramp.inputs["Fac"])
        links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])
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
    gunmetal = material(
        "Oiled gunmetal",
        (0.025, 0.032, 0.038, 1.0),
        metallic=0.82,
        roughness=0.43,
        brushed=True,
    )
    lab_panel = material(
        "Powder-coated laboratory steel",
        (0.018, 0.025, 0.032, 1.0),
        metallic=0.55,
        roughness=0.58,
        brushed=True,
    )
    inspection_light = material(
        "Cold inspection luminaire",
        (0.68, 0.82, 0.92, 1.0),
        roughness=0.18,
        emission=(0.62, 0.82, 1.0, 1.0),
        emission_strength=6.5,
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

    # Load-bearing isolation feet and exposed retaining hardware.
    for x in (-1.68, 1.68):
        for y in (-1.25, 1.25):
            cylinder(
                f"Vibration isolator {x:+.0f} {y:+.0f}",
                (x, y, -0.015),
                0.22,
                0.13,
                rubber,
                pedestal,
                bevel=0.025,
            )
            cylinder(
                f"Isolator washer {x:+.0f} {y:+.0f}",
                (x, y, 0.055),
                0.15,
                0.035,
                brass,
                pedestal,
                bevel=0.008,
            )

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

    # Front inspection ports, diaphragms, iris vanes, and fasteners.
    iris_vanes: list[tuple[bpy.types.Object, float]] = []
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
        torus(
            f"{side_name} iris guide",
            (x, -0.755, z),
            0.205,
            0.018,
            gunmetal,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
        )
        for vane_index in range(9):
            angle = math.tau * vane_index / 9.0
            vane = rounded_box(
                f"{side_name} iris vane {vane_index + 1:02d}",
                (
                    x + 0.11 * math.cos(angle),
                    -0.775,
                    z + 0.11 * math.sin(angle),
                ),
                (0.18, 0.022, 0.052),
                0.011,
                dark_titanium if vane_index % 2 else titanium,
                mechanisms,
                rotation=(0.0, -angle + math.radians(18), 0.0),
            )
            iris_vanes.append((vane, vane.rotation_euler.y))
            cylinder(
                f"{side_name} iris pivot {vane_index + 1:02d}",
                (
                    x + 0.215 * math.cos(angle),
                    -0.79,
                    z + 0.215 * math.sin(angle),
                ),
                0.017,
                0.026,
                brass,
                mechanisms,
                rotation=(math.radians(90), 0.0, 0.0),
                vertices=16,
                bevel=0.004,
            )
        cylinder(
            f"{side_name} iris hub",
            (x, -0.79, z),
            0.055,
            0.035,
            brass,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
            bevel=0.008,
        )
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
        text_object(
            f"{side_name} pump marking",
            "LV PUMP" if side_name == "Arterial" else "RV PUMP",
            (x, -0.805, z - 0.45),
            0.055,
            white,
            labels,
            extrude=0.003,
        )

    # Shell service seams, flush rivets, and lateral cooling banks make the
    # chambers read as manufactured pressure vessels rather than smooth toys.
    for side_name, x, sign in (("Left", -0.38, -1), ("Right", 0.48, 1)):
        seam_points = [
            (x + sign * 0.38, -0.52, 1.52),
            (x + sign * 0.57, -0.54, 1.94),
            (x + sign * 0.59, -0.50, 2.46),
            (x + sign * 0.43, -0.43, 2.85),
        ]
        curve_tube(f"{side_name} shell service seam", seam_points, 0.018, rubber, core, resolution=2)
        for rivet_index, seam_point in enumerate(seam_points):
            cylinder(
                f"{side_name} seam rivet {rivet_index + 1}",
                (seam_point[0], seam_point[1] - 0.025, seam_point[2]),
                0.023,
                0.025,
                brass,
                core,
                rotation=(math.radians(90), 0.0, 0.0),
                vertices=16,
                bevel=0.004,
            )
        for fin_index in range(6):
            rounded_box(
                f"{side_name} cooling fin {fin_index + 1}",
                (x + sign * 0.78, 0.08, 1.60 + fin_index * 0.24),
                (0.075, 0.50, 0.13),
                0.018,
                gunmetal if fin_index % 2 == 0 else dark_titanium,
                mechanisms,
                rotation=(0.0, math.radians(sign * 4), 0.0),
            )
        rounded_box(
            f"{side_name} cooling manifold",
            (x + sign * 0.79, 0.08, 2.20),
            (0.11, 0.25, 1.58),
            0.025,
            brass,
            mechanisms,
        )

    # Bolted lower access panels and a ribbed sternum rail break up the
    # remaining uninterrupted shell surfaces.
    for panel_name, panel_x, panel_z, panel_rotation in (
        ("Left ventricular service plate", -0.42, 1.48, -5),
        ("Right ventricular service plate", 0.43, 1.58, 6),
    ):
        rounded_box(
            panel_name,
            (panel_x, -0.585, panel_z),
            (0.42, 0.055, 0.25),
            0.035,
            gunmetal,
            mechanisms,
            rotation=(0.0, math.radians(panel_rotation), 0.0),
        )
        for bolt_index, (bolt_dx, bolt_dz) in enumerate(
            ((-0.16, -0.085), (0.16, -0.085), (-0.16, 0.085), (0.16, 0.085)),
            start=1,
        ):
            cylinder(
                f"{panel_name} bolt {bolt_index}",
                (panel_x + bolt_dx, -0.625, panel_z + bolt_dz),
                0.018,
                0.026,
                brass,
                mechanisms,
                rotation=(math.radians(90), 0.0, 0.0),
                vertices=16,
                bevel=0.004,
            )
    rounded_box(
        "Sternum transmission rail",
        (0.02, -0.63, 1.45),
        (0.12, 0.09, 0.83),
        0.025,
        brass,
        mechanisms,
    )
    for rib_index in range(6):
        rounded_box(
            f"Sternum reinforcing rib {rib_index + 1}",
            (0.02, -0.685, 1.13 + rib_index * 0.13),
            (0.43, 0.045, 0.052),
            0.012,
            titanium if rib_index % 2 == 0 else dark_titanium,
            mechanisms,
        )
    text_object(
        "Core housing marking",
        "CORE 7",
        (0.02, -0.718, 1.93),
        0.052,
        warning,
        labels,
        extrude=0.003,
    )

    # Layered upper armor, removable cheek plates, and recessed fasteners.
    for plate_name, plate_x, plate_z, plate_angle in (
        ("Left atrial servo cover", -0.48, 2.78, -11),
        ("Right atrial servo cover", 0.54, 2.82, 9),
    ):
        rounded_box(
            plate_name,
            (plate_x, -0.515, plate_z),
            (0.50, 0.060, 0.19),
            0.045,
            dark_titanium,
            mechanisms,
            rotation=(0.0, math.radians(plate_angle), 0.0),
        )
        rounded_box(
            f"{plate_name} inset",
            (plate_x, -0.555, plate_z),
            (0.34, 0.025, 0.075),
            0.018,
            gunmetal,
            mechanisms,
            rotation=(0.0, math.radians(plate_angle), 0.0),
        )
        for bolt_index, bolt_dx in enumerate((-0.19, 0.19), start=1):
            cylinder(
                f"{plate_name} fastener {bolt_index}",
                (plate_x + bolt_dx, -0.575, plate_z),
                0.021,
                0.026,
                brass,
                mechanisms,
                rotation=(math.radians(90), 0.0, 0.0),
                vertices=6,
                bevel=0.004,
            )

    # Exposed front crank train: a toothed flywheel, six spokes, twin cam pins,
    # and articulated connecting rods that visibly convert rotation into pulse.
    front_flywheel_center = Vector((0.02, -0.82, 1.16))
    front_flywheel_ring = torus(
        "Anterior pulse flywheel",
        front_flywheel_center,
        0.30,
        0.045,
        brass,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
    )
    front_flywheel_teeth: list[tuple[bpy.types.Object, float]] = []
    for tooth_index in range(16):
        tooth_angle = math.tau * tooth_index / 16.0
        tooth = rounded_box(
            f"Anterior flywheel tooth {tooth_index + 1:02d}",
            (
                front_flywheel_center.x + 0.38 * math.cos(tooth_angle),
                front_flywheel_center.y,
                front_flywheel_center.z + 0.38 * math.sin(tooth_angle),
            ),
            (0.095, 0.065, 0.055),
            0.012,
            gunmetal if tooth_index % 2 else titanium,
            mechanisms,
            rotation=(0.0, -tooth_angle, 0.0),
        )
        front_flywheel_teeth.append((tooth, tooth_angle))
    front_flywheel_spokes: list[tuple[bpy.types.Object, float]] = []
    for spoke_index in range(6):
        spoke_angle = math.tau * spoke_index / 6.0
        spoke_end = (
            front_flywheel_center.x + 0.265 * math.cos(spoke_angle),
            front_flywheel_center.y,
            front_flywheel_center.z + 0.265 * math.sin(spoke_angle),
        )
        spoke = cylinder_between(
            f"Anterior flywheel spoke {spoke_index + 1}",
            front_flywheel_center,
            spoke_end,
            0.025,
            titanium,
            mechanisms,
            vertices=20,
        )
        front_flywheel_spokes.append((spoke, spoke_angle))
    cylinder(
        "Anterior flywheel bearing housing",
        (front_flywheel_center.x, front_flywheel_center.y + 0.03, front_flywheel_center.z),
        0.105,
        0.20,
        gunmetal,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
        bevel=0.018,
    )
    front_flywheel_hub = cylinder(
        "Anterior flywheel hub cap",
        (front_flywheel_center.x, front_flywheel_center.y - 0.09, front_flywheel_center.z),
        0.072,
        0.045,
        warning,
        mechanisms,
        rotation=(math.radians(90), 0.0, 0.0),
        bevel=0.012,
    )
    front_cam_pins: list[
        tuple[bpy.types.Object, bpy.types.Object, float]
    ] = []
    front_linkages: list[
        tuple[bpy.types.Object, Vector, float, float]
    ] = []
    for linkage_index, (base_angle, fixed_endpoint) in enumerate(
        (
            (0.0, Vector((-0.30, -0.72, 1.55))),
            (math.pi, Vector((0.34, -0.72, 1.64))),
        ),
        start=1,
    ):
        cam_position = Vector(
            (
                front_flywheel_center.x + 0.17 * math.cos(base_angle),
                front_flywheel_center.y - 0.055,
                front_flywheel_center.z + 0.17 * math.sin(base_angle),
            )
        )
        cam_pin = cylinder(
            f"Anterior crank pin {linkage_index}",
            cam_position,
            0.044,
            0.055,
            brass,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
            bevel=0.008,
        )
        linkage = cylinder_between(
            f"Anterior articulated linkage {linkage_index}",
            cam_position,
            fixed_endpoint,
            0.027,
            titanium,
            mechanisms,
            vertices=24,
        )
        front_linkages.append(
            (linkage, fixed_endpoint, base_angle, (fixed_endpoint - cam_position).length)
        )
        crank_joint = uv_sphere(
            f"Anterior linkage {linkage_index} crank joint",
            cam_position,
            (0.058, 0.058, 0.058),
            brass,
            mechanisms,
            segments=24,
            rings=12,
        )
        front_cam_pins.append((cam_pin, crank_joint, base_angle))
        uv_sphere(
            f"Anterior linkage {linkage_index} rocker joint",
            fixed_endpoint,
            (0.058, 0.058, 0.058),
            titanium,
            mechanisms,
            segments=24,
            rings=12,
        )

    # Front valve bridge and four manual trim wheels.
    cylinder_between(
        "Atrial valve bridge",
        (-0.90, -0.46, 3.48),
        (0.92, -0.46, 3.48),
        0.065,
        gunmetal,
        mechanisms,
        vertices=32,
    )
    for valve_index, valve_x in enumerate((-0.68, -0.23, 0.24, 0.69), start=1):
        cylinder(
            f"Trim valve stem {valve_index}",
            (valve_x, -0.50, 3.48),
            0.025,
            0.20,
            brass,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
            vertices=20,
        )
        torus(
            f"Trim handwheel {valve_index}",
            (valve_x, -0.62, 3.48),
            0.105,
            0.018,
            warning if valve_index in (1, 4) else titanium,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
        )
        for spoke_index in range(4):
            wheel_angle = math.tau * spoke_index / 4.0
            cylinder_between(
                f"Trim handwheel {valve_index} spoke {spoke_index + 1}",
                (valve_x, -0.62, 3.48),
                (
                    valve_x + 0.088 * math.cos(wheel_angle),
                    -0.62,
                    3.48 + 0.088 * math.sin(wheel_angle),
                ),
                0.009,
                brass,
                mechanisms,
                vertices=12,
            )
        curve_tube(
            f"Trim valve feed {valve_index}",
            [
                (valve_x, -0.44, 3.48),
                (valve_x * 0.88, -0.31, 3.23),
                (valve_x * 0.78, -0.24, 3.02),
            ],
            0.021,
            brass,
            vascular,
            resolution=2,
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

    # Calibrated pressure accumulators with visible working fluid.
    for side_name, sign, flow_mat in (
        ("Arterial", -1, arterial),
        ("Venous", 1, venous),
    ):
        accumulator_x = sign * 1.30
        accumulator_y = 0.64
        accumulator_z = 3.42
        cylinder(
            f"{side_name} accumulator glass",
            (accumulator_x, accumulator_y, accumulator_z),
            0.17,
            0.82,
            glass,
            vascular,
            bevel=0.012,
        )
        cylinder(
            f"{side_name} accumulator fluid",
            (accumulator_x, accumulator_y, accumulator_z - 0.08),
            0.115,
            0.58,
            flow_mat,
            vascular,
        )
        for cap_index, cap_z in enumerate((3.00, 3.84)):
            cylinder(
                f"{side_name} accumulator cap {cap_index + 1}",
                (accumulator_x, accumulator_y, cap_z),
                0.21,
                0.10,
                brass,
                vascular,
                bevel=0.018,
            )
        curve_tube(
            f"{side_name} accumulator feed",
            [
                (accumulator_x, accumulator_y, 3.00),
                (sign * 1.18, 0.45, 2.80),
                (sign * 0.78, 0.30, 2.62),
            ],
            0.045,
            gunmetal,
            vascular,
            resolution=3,
        )
        torus(
            f"{side_name} accumulator collar",
            (accumulator_x, accumulator_y, 3.72),
            0.18,
            0.025,
            titanium,
            vascular,
        )
        for coil_index in range(5):
            torus(
                f"{side_name} accumulator retention coil {coil_index + 1}",
                (accumulator_x, accumulator_y, 3.15 + coil_index * 0.14),
                0.19,
                0.014,
                brass,
                vascular,
            )
        rounded_box(
            f"{side_name} accumulator scale",
            (accumulator_x + sign * 0.20, accumulator_y - 0.02, 3.42),
            (0.035, 0.055, 0.62),
            0.008,
            titanium,
            labels,
        )
        for tick_index in range(7):
            rounded_box(
                f"{side_name} accumulator tick {tick_index + 1}",
                (
                    accumulator_x + sign * 0.225,
                    accumulator_y - 0.055,
                    3.15 + tick_index * 0.09,
                ),
                (0.060, 0.018, 0.010),
                0.002,
                white,
                labels,
            )

    # Braided-looking service harnesses route power and sensor lines to the bed.
    for harness_index, (sign, lateral_offset) in enumerate(
        ((-1, -0.10), (-1, 0.08), (1, -0.08), (1, 0.11)),
        start=1,
    ):
        curve_tube(
            f"Service harness {harness_index}",
            [
                (sign * (0.64 + lateral_offset), 0.38, 2.94),
                (sign * (0.98 + lateral_offset), 0.54, 2.30),
                (sign * (1.14 + lateral_offset), 0.48, 1.35),
                (sign * (1.32 + lateral_offset), 0.20, 0.70),
            ],
            0.027,
            rubber,
            vascular,
            resolution=2,
        )

    # Twin hydraulic manifolds distribute pressure to the four linear rams.
    manifold_needles: list[bpy.types.Object] = []
    for side_name, sign, flow_mat in (
        ("Arterial", -1, arterial),
        ("Venous", 1, venous),
    ):
        manifold_x = sign * 1.56
        rounded_box(
            f"{side_name} hydraulic manifold",
            (manifold_x, -0.18, 2.18),
            (0.22, 0.28, 1.34),
            0.055,
            gunmetal,
            mechanisms,
        )
        for port_index, port_z in enumerate((1.72, 2.02, 2.32, 2.62), start=1):
            cylinder(
                f"{side_name} manifold port {port_index}",
                (manifold_x - sign * 0.13, -0.20, port_z),
                0.060,
                0.11,
                brass,
                mechanisms,
                rotation=(0.0, math.radians(90), 0.0),
                bevel=0.010,
            )
            curve_tube(
                f"{side_name} manifold pressure line {port_index}",
                [
                    (manifold_x - sign * 0.18, -0.20, port_z),
                    (sign * 1.25, -0.13, port_z),
                    (sign * 0.92, -0.06, port_z - 0.04),
                ],
                0.022,
                flow_mat if port_index in (1, 4) else brass,
                vascular,
                resolution=2,
            )
        gauge_z = 2.96
        cylinder(
            f"{side_name} manifold gauge bezel",
            (manifold_x, -0.36, gauge_z),
            0.19,
            0.11,
            brass,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
            bevel=0.020,
        )
        cylinder(
            f"{side_name} manifold gauge face",
            (manifold_x, -0.425, gauge_z),
            0.15,
            0.020,
            ceramic,
            mechanisms,
            rotation=(math.radians(90), 0.0, 0.0),
        )
        for tick_index in range(7):
            tick_angle = math.radians(-60 + tick_index * 20)
            rounded_box(
                f"{side_name} manifold gauge tick {tick_index + 1}",
                (
                    manifold_x + 0.115 * math.sin(tick_angle),
                    -0.445,
                    gauge_z + 0.115 * math.cos(tick_angle),
                ),
                (0.012, 0.012, 0.038),
                0.003,
                white,
                mechanisms,
                rotation=(0.0, tick_angle, 0.0),
            )
        manifold_needle = rounded_box(
            f"{side_name} manifold needle",
            (manifold_x, -0.45, gauge_z),
            (0.018, 0.018, 0.125),
            0.006,
            warning,
            mechanisms,
            rotation=(0.0, math.radians(-20 if sign < 0 else 16), 0.0),
        )
        manifold_needle["manifold_side"] = side_name
        manifold_needles.append(manifold_needle)

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
            cylinder(
                f"{side} actuator end collar {level_index + 1}",
                (sign * 1.73, 0.06, z),
                0.145,
                0.085,
                brass,
                mechanisms,
                rotation=(0.0, math.radians(90), 0.0),
                bevel=0.018,
            )
            cylinder(
                f"{side} actuator end cap {level_index + 1}",
                (sign * 1.78, 0.06, z),
                0.095,
                0.035,
                titanium,
                mechanisms,
                rotation=(0.0, math.radians(90), 0.0),
                vertices=28,
                bevel=0.012,
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
        # Articulated restraint arm transfers pulse load into the rear frame.
        clamp_start = (sign * 1.48, 0.70, 3.24)
        clamp_joint = (sign * 1.11, 0.46, 3.13)
        clamp_end = (sign * 0.78, 0.24, 3.03)
        cylinder_between(
            f"Upper restraint arm outer {'L' if sign < 0 else 'R'}",
            clamp_start,
            clamp_joint,
            0.052,
            gunmetal,
            frame,
        )
        cylinder_between(
            f"Upper restraint arm inner {'L' if sign < 0 else 'R'}",
            clamp_joint,
            clamp_end,
            0.043,
            brass,
            frame,
        )
        uv_sphere(
            f"Restraint spherical joint {'L' if sign < 0 else 'R'}",
            clamp_joint,
            (0.11, 0.11, 0.11),
            titanium,
            frame,
            segments=28,
            rings=14,
        )
        torus(
            f"Atrial restraint collar {'L' if sign < 0 else 'R'}",
            clamp_end,
            0.105,
            0.028,
            brass,
            frame,
            rotation=(math.radians(90), 0.0, 0.0),
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

    # Rear electrical bus and ceramic isolation stack remain visible through
    # the gaps in the heart, giving the device believable service depth.
    for rail_index, (rail_z, rail_mat) in enumerate(
        ((1.04, brass), (1.28, titanium)),
        start=1,
    ):
        cylinder_between(
            f"Rear power bus rail {rail_index}",
            (-1.24, 0.88, rail_z),
            (1.24, 0.88, rail_z),
            0.045,
            rail_mat,
            frame,
            vertices=28,
        )
    for insulator_index, insulator_x in enumerate((-1.05, -0.52, 0.0, 0.52, 1.05), start=1):
        cylinder(
            f"Rear ceramic isolator {insulator_index}",
            (insulator_x, 0.88, 1.16),
            0.070,
            0.32,
            ceramic,
            frame,
            bevel=0.012,
        )
        for flange_index, flange_z in enumerate((1.04, 1.16, 1.28), start=1):
            torus(
                f"Rear isolator {insulator_index} flange {flange_index}",
                (insulator_x, 0.88, flange_z),
                0.085,
                0.014,
                titanium,
                frame,
            )
    for lead_index, (sign, endpoint_z) in enumerate(
        ((-1, 1.78), (-1, 2.62), (1, 1.78), (1, 2.62)),
        start=1,
    ):
        curve_tube(
            f"Pulse solenoid power lead {lead_index}",
            [
                (sign * 0.82, 0.88, 1.28),
                (sign * 1.18, 0.72, 1.42 + (endpoint_z - 1.78) * 0.35),
                (sign * 1.46, 0.28, endpoint_z),
            ],
            0.020,
            rubber,
            frame,
            resolution=2,
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

    # The iris valves snap open on each ventricular pressure peak.
    for vane, base_rotation in iris_vanes:
        for start in pulse_frames[:-1]:
            for offset, angle_delta in (
                (0, 0.0),
                (8, math.radians(13)),
                (14, math.radians(-3)),
                (24, 0.0),
            ):
                vane.rotation_euler.y = base_rotation + angle_delta
                vane.keyframe_insert("rotation_euler", frame=start + offset, index=1)

    # The anterior crank train completes one revolution per heartbeat. Every
    # visible element is keyed directly so the editable file stays robust.
    flywheel_keyframes = [
        (1 + quarter_index * 9, quarter_index * math.pi * 0.5)
        for quarter_index in range(16)
    ]
    flywheel_keyframes.append((144, math.tau * 4.0))
    for frame_number, angle_delta in flywheel_keyframes:
        front_flywheel_ring.rotation_euler.y = angle_delta
        front_flywheel_ring.keyframe_insert("rotation_euler", frame=frame_number, index=1)
        front_flywheel_hub.rotation_euler.y = angle_delta
        front_flywheel_hub.keyframe_insert("rotation_euler", frame=frame_number, index=1)
        for tooth, base_angle in front_flywheel_teeth:
            angle = base_angle + angle_delta
            tooth.location = (
                front_flywheel_center.x + 0.38 * math.cos(angle),
                front_flywheel_center.y,
                front_flywheel_center.z + 0.38 * math.sin(angle),
            )
            tooth.rotation_euler.y = -angle
            tooth.keyframe_insert("location", frame=frame_number)
            tooth.keyframe_insert("rotation_euler", frame=frame_number, index=1)
        for spoke, base_angle in front_flywheel_spokes:
            angle = base_angle + angle_delta
            spoke_start = front_flywheel_center
            spoke_end = Vector(
                (
                    front_flywheel_center.x + 0.265 * math.cos(angle),
                    front_flywheel_center.y,
                    front_flywheel_center.z + 0.265 * math.sin(angle),
                )
            )
            spoke_direction = spoke_end - spoke_start
            spoke.location = (spoke_start + spoke_end) * 0.5
            spoke.rotation_quaternion = spoke_direction.to_track_quat("Z", "Y")
            spoke.keyframe_insert("location", frame=frame_number)
            spoke.keyframe_insert("rotation_quaternion", frame=frame_number)
        for cam_pin, crank_joint, base_angle in front_cam_pins:
            angle = base_angle + angle_delta
            cam_position = Vector(
                (
                    front_flywheel_center.x + 0.17 * math.cos(angle),
                    front_flywheel_center.y - 0.055,
                    front_flywheel_center.z + 0.17 * math.sin(angle),
                )
            )
            cam_pin.location = cam_position
            crank_joint.location = cam_position
            cam_pin.keyframe_insert("location", frame=frame_number)
            crank_joint.keyframe_insert("location", frame=frame_number)
        for linkage, fixed_endpoint, base_angle, base_length in front_linkages:
            angle = base_angle + angle_delta
            cam_position = Vector(
                (
                    front_flywheel_center.x + 0.17 * math.cos(angle),
                    front_flywheel_center.y - 0.055,
                    front_flywheel_center.z + 0.17 * math.sin(angle),
                )
            )
            linkage_direction = fixed_endpoint - cam_position
            linkage.location = (fixed_endpoint + cam_position) * 0.5
            linkage.rotation_quaternion = linkage_direction.to_track_quat("Z", "Y")
            linkage.scale.z = linkage_direction.length / base_length
            linkage.keyframe_insert("location", frame=frame_number)
            linkage.keyframe_insert("rotation_quaternion", frame=frame_number)
            linkage.keyframe_insert("scale", frame=frame_number)

    # Secondary gauge needles lag the main pulse slightly, like damped
    # mechanical instruments rather than synchronized UI indicators.
    for needle_index, needle in enumerate(manifold_needles):
        side_offset = 3 if needle_index else 0
        base_angle = math.radians(-18 if needle_index == 0 else 14)
        for start in pulse_frames[:-1]:
            for offset, angle_delta in (
                (0, 0.0),
                (9 + side_offset, math.radians(31)),
                (17 + side_offset, math.radians(12)),
                (27, 0.0),
            ):
                needle.rotation_euler.y = base_angle + angle_delta
                needle.keyframe_insert("rotation_euler", frame=start + offset, index=1)

    # Direct tooth animation keeps the timing wheel mechanically centered.
    timing_keyframes = (
        (1, 0.0),
        (37, math.pi * 0.5),
        (73, math.pi),
        (109, math.pi * 1.5),
        (144, math.tau),
    )
    for tooth_index, tooth in enumerate(timing_teeth):
        base_angle = math.tau * tooth_index / len(timing_teeth)
        for frame_number, angle_delta in timing_keyframes:
            angle = base_angle + angle_delta
            tooth.location = (
                gear_center.x + 0.66 * math.cos(angle),
                gear_center.y,
                gear_center.z + 0.66 * math.sin(angle),
            )
            tooth.rotation_euler.y = -angle
            tooth.keyframe_insert("location", frame=frame_number)
            tooth.keyframe_insert("rotation_euler", frame=frame_number, index=1)

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

    # Floor, segmented laboratory wall, and cinematic lighting.
    floor = rounded_box(
        "Laboratory floor",
        (0.0, 0.0, -0.16),
        (12.0, 12.0, 0.24),
        0.05,
        ceramic,
        lighting,
    )
    for panel_index, panel_x in enumerate((-3.0, 0.0, 3.0), start=1):
        rounded_box(
            f"Laboratory wall panel {panel_index}",
            (panel_x, 3.15, 2.65),
            (2.82, 0.18, 5.55),
            0.08,
            lab_panel,
            lighting,
        )
        rounded_box(
            f"Wall panel service channel {panel_index}",
            (panel_x, 3.045, 2.63),
            (0.12, 0.045, 4.70),
            0.018,
            gunmetal,
            lighting,
        )
        for bolt_index, (bolt_x, bolt_z) in enumerate(
            (
                (panel_x - 1.22, 0.40),
                (panel_x + 1.22, 0.40),
                (panel_x - 1.22, 4.90),
                (panel_x + 1.22, 4.90),
            ),
            start=1,
        ):
            cylinder(
                f"Wall panel {panel_index} anchor {bolt_index}",
                (bolt_x, 3.04, bolt_z),
                0.055,
                0.045,
                titanium,
                lighting,
                rotation=(math.radians(90), 0.0, 0.0),
                vertices=20,
                bevel=0.008,
            )
    for conduit_index, x in enumerate((-2.05, 2.05), start=1):
        cylinder_between(
            f"Wall utility conduit {conduit_index}",
            (x, 3.00, 0.25),
            (x, 3.00, 5.05),
            0.055,
            gunmetal,
            lighting,
            vertices=24,
        )
        for clamp_index, z in enumerate((0.85, 2.65, 4.45), start=1):
            torus(
                f"Wall conduit clamp {conduit_index}-{clamp_index}",
                (x, 3.00, z),
                0.075,
                0.018,
                brass,
                lighting,
            )
    rounded_box(
        "Overhead inspection luminaire",
        (0.0, 2.92, 5.72),
        (4.4, 0.09, 0.13),
        0.035,
        inspection_light,
        lighting,
    )
    for light_index, light_x in enumerate((-2.54, 2.54), start=1):
        rounded_box(
            f"Vertical service luminaire {light_index}",
            (light_x, 2.94, 3.18),
            (0.10, 0.065, 1.42),
            0.028,
            inspection_light,
            lighting,
        )
        rounded_box(
            f"Vertical luminaire housing {light_index}",
            (light_x, 3.00, 3.18),
            (0.20, 0.12, 1.58),
            0.035,
            gunmetal,
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
    area_light("Wall inspection bounce", (0.0, 2.45, 4.85), 340.0, (0.56, 0.76, 1.0), 2.6, (0.0, 0.0, 2.35))

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
