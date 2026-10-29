import trimesh
import numpy as np
from pathlib import Path

fbx_path = Path("C:/Users/ram/Downloads/low-poly-hospital/source/Hospital.fbx")
print(f"Loading FBX from: {fbx_path}")

try:
    scene = trimesh.load(str(fbx_path))
    print(f"Loaded scene type: {type(scene)}")
    if isinstance(scene, trimesh.Scene):
        print(f"Geometries in scene: {list(scene.geometry.keys())}")
        bounds = scene.bounds
        extents = scene.extents
        print(f"Scene bounds: min={bounds[0]}, max={bounds[1]}")
        print(f"Scene extents (size): width={extents[0]:.2f}, height={extents[1]:.2f}, depth={extents[2]:.2f}")
        for name, geom in scene.geometry.items():
            print(f"  Geom '{name}': vertices={len(geom.vertices)}, faces={len(geom.faces)}, bounds min={geom.bounds[0]}, max={geom.bounds[1]}")
    elif isinstance(scene, trimesh.Trimesh):
        print(f"Single mesh: vertices={len(scene.vertices)}, faces={len(scene.faces)}")
        print(f"Bounds: min={scene.bounds[0]}, max={scene.bounds[1]}")
        print(f"Extents: {scene.extents}")
except Exception as e:
    print(f"Trimesh error: {e}")
