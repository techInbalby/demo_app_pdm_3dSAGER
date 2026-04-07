"""
Arun et al. (1987) rigid alignment utilities.

Reference:
K. S. Arun, T. S. Huang, and S. D. Blostein.
"Least-Squares Fitting of Two 3-D Point Sets" (1987).
"""

from __future__ import annotations

import numpy as np


def estimate_rigid_transform_3d(source_points, target_points):
    """
    Estimate rigid transform (R, t) that maps source_points to target_points.

    Uses the SVD-based least-squares method from Arun et al. (1987):
        target ~= R @ source + t

    Args:
        source_points: iterable of shape (N, 3)
        target_points: iterable of shape (N, 3)

    Returns:
        dict with:
            rotation: (3, 3) ndarray
            translation: (3,) ndarray
            rmse: float
            residuals: (N,) ndarray Euclidean residual norms
    """
    src = np.asarray(source_points, dtype=np.float64)
    tgt = np.asarray(target_points, dtype=np.float64)

    if src.shape != tgt.shape or src.ndim != 2 or src.shape[1] != 3:
        raise ValueError("source_points and target_points must both be shape (N, 3)")
    if src.shape[0] < 3:
        raise ValueError("At least 3 anchor points are required")

    src_centroid = src.mean(axis=0)
    tgt_centroid = tgt.mean(axis=0)

    src_centered = src - src_centroid
    tgt_centered = tgt - tgt_centroid

    h = src_centered.T @ tgt_centered
    u, _, vt = np.linalg.svd(h)

    r = vt.T @ u.T

    # Reflection case: enforce proper rotation (det(R) = +1)
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1
        r = vt.T @ u.T

    t = tgt_centroid - (r @ src_centroid)

    transformed = (r @ src.T).T + t
    residuals = np.linalg.norm(transformed - tgt, axis=1)
    rmse = float(np.sqrt(np.mean(np.square(residuals))))

    return {
        "rotation": r,
        "translation": t,
        "rmse": rmse,
        "residuals": residuals,
    }


def apply_rigid_transform(points, rotation, translation):
    """
    Apply rigid transform to Nx3 points.
    """
    pts = np.asarray(points, dtype=np.float64)
    rot = np.asarray(rotation, dtype=np.float64)
    trn = np.asarray(translation, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError("points must be shape (N, 3)")
    if rot.shape != (3, 3):
        raise ValueError("rotation must be shape (3, 3)")
    if trn.shape != (3,):
        raise ValueError("translation must be shape (3,)")
    return (rot @ pts.T).T + trn
