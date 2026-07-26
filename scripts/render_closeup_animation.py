"""Render a safe, cinematic close-up of the MACHINA CORDIS animation."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "machina-cordis-closeup.mp4"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution", type=int, default=720)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--preview", type=Path)
    blender_separator = sys.argv.index("--") + 1 if "--" in sys.argv else len(sys.argv)
    return parser.parse_args(sys.argv[blender_separator:])


def configure_camera(scene: bpy.types.Scene) -> bpy.types.Object:
    old_camera = bpy.data.objects.get("MACHINA CORDIS camera")
    camera_data = bpy.data.cameras.new("Cinematic closeup lens")
    camera = bpy.data.objects.new("Cinematic closeup camera", camera_data)
    scene.collection.objects.link(camera)

    target = bpy.data.objects.new("Cinematic focus target", None)
    target.empty_display_type = "SPHERE"
    target.empty_display_size = 0.12
    target.location = (0.02, -0.02, 2.30)
    scene.collection.objects.link(target)

    camera_data.lens = 61
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.focus_object = target
    camera_data.dof.aperture_fstop = 6.3

    tracking = camera.constraints.new(type="TRACK_TO")
    tracking.name = "Track reactor core"
    tracking.target = target
    tracking.track_axis = "TRACK_NEGATIVE_Z"
    tracking.up_axis = "UP_Y"

    camera_positions = (
        (1, (5.25, -6.55, 4.55)),
        (54, (6.05, -5.85, 4.28)),
        (108, (5.15, -6.62, 4.48)),
    )
    for frame, location in camera_positions:
        camera.location = location
        camera.keyframe_insert("location", frame=frame)

    if old_camera:
        old_camera.hide_render = True
    scene.camera = camera
    return camera


def configure_render(scene: bpy.types.Scene, args: argparse.Namespace) -> None:
    scene.frame_start = 1
    scene.frame_end = 108
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.render.fps_base = 1.0
    scene.render.film_transparent = False

    scene.eevee.taa_render_samples = args.samples
    scene.eevee.use_shadows = True
    scene.eevee.shadow_resolution_scale = 0.75
    scene.eevee.volumetric_samples = 16

    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.10


def render_preview(scene: bpy.types.Scene, preview_path: Path) -> None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    scene.frame_set(48)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(preview_path)
    bpy.ops.render.render(write_still=True)
    print(f"Cinematic preview rendered: {preview_path}")


def render_animation(scene: bpy.types.Scene, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="machina-cordis-closeup-") as frames_dir:
        frames_path = Path(frames_dir)
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.color_depth = "8"
        scene.render.image_settings.compression = 35
        scene.render.filepath = str(frames_path / "frame-")
        bpy.ops.render.render(animation=True)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "warning",
                "-framerate",
                "24",
                "-start_number",
                "1",
                "-i",
                str(frames_path / "frame-%04d.png"),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output_path),
            ],
            check=True,
        )
    print(f"Cinematic animation rendered: {output_path}")


def main() -> None:
    args = arguments()
    scene = bpy.context.scene
    configure_camera(scene)
    configure_render(scene, args)
    if args.preview:
        render_preview(scene, args.preview.resolve())
    else:
        render_animation(scene, args.output.resolve())


if __name__ == "__main__":
    main()
