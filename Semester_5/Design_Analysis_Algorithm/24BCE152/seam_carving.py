
from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Tuple, Union

import numpy as np
from PIL import Image

try:
    import numba
    HAS_NUMBA = True
except Exception:
    HAS_NUMBA = False


if HAS_NUMBA:
    @numba.njit(fastmath=True)
    def _fast_dual_gradient(img: np.ndarray) -> np.ndarray:
        h, w, c = img.shape
        energy = np.zeros((h, w), dtype=np.float32)
        for i in range(h):
            i_prev = max(0, i - 1)
            i_next = min(h - 1, i + 1)
            for j in range(w):
                j_prev = max(0, j - 1)
                j_next = min(w - 1, j + 1)
                dx2 = 0.0
                dy2 = 0.0
                for ch in range(c):
                    diff_x = (float(img[i, j_next, ch]) - float(img[i, j_prev, ch])) * 0.5
                    diff_y = (float(img[i_next, j, ch]) - float(img[i_prev, j, ch])) * 0.5
                    dx2 += diff_x * diff_x
                    dy2 += diff_y * diff_y
                energy[i, j] = np.sqrt(dx2 + dy2)
        return energy

    @numba.njit(fastmath=True)
    def _fast_find_seam(energy: np.ndarray) -> np.ndarray:
        h, w = energy.shape
        dp = energy.copy()
        backtrack = np.zeros((h, w), dtype=np.int32)

        for i in range(1, h):
            for j in range(w):
                best = dp[i - 1, j]
                choice = 0
                if j > 0 and dp[i - 1, j - 1] < best:
                    best = dp[i - 1, j - 1]
                    choice = -1
                if j < w - 1 and dp[i - 1, j + 1] < best:
                    best = dp[i - 1, j + 1]
                    choice = 1
                dp[i, j] += best
                backtrack[i, j] = choice

        seam = np.empty(h, dtype=np.int32)
        min_idx = 0
        min_val = dp[h - 1, 0]
        for j in range(1, w):
            if dp[h - 1, j] < min_val:
                min_val = dp[h - 1, j]
                min_idx = j
        seam[h - 1] = min_idx

        for i in range(h - 2, -1, -1):
            seam[i] = seam[i + 1] + backtrack[i + 1, seam[i + 1]]

        return seam


@dataclass
class CarveMetrics:
    original_width: int
    original_height: int
    compressed_width: int
    compressed_height: int
    vertical_seams_removed: int
    horizontal_seams_removed: int
    total_pixels_removed: int
    pixel_reduction_percent: float
    original_bytes_png: int
    compressed_bytes_png: int
    byte_compression_ratio: float
    total_time_seconds: float
    seams_per_second: float
    initial_average_energy: float
    final_average_energy: float
    energy_density_change_percent: float
    energy_method: str


class SeamCarver:
    """Core Seam Carving algorithm engine using Dual Gradient Energy."""

    def __init__(self, image: Union[np.ndarray, Image.Image], energy_method: str = "dual_gradient"):
        if isinstance(image, Image.Image):
            self.original_image = np.array(image.convert("RGB"), dtype=np.uint8)
        else:
            self.original_image = np.array(image, dtype=np.uint8)
            if self.original_image.ndim == 2:
                self.original_image = np.stack([self.original_image] * 3, axis=-1)
            elif self.original_image.shape[2] == 4:
                self.original_image = self.original_image[:, :, :3]

        self.current_image = self.original_image.copy()
        self.energy_method = "dual_gradient"

        h, w, _ = self.original_image.shape
        self.original_coords = np.arange(h * w).reshape((h, w))
        self.seam_mask = np.zeros((h, w), dtype=bool)
        self.seam_order_mask = np.full((h, w), -1, dtype=np.int32)
        self.seams_removed_count = 0

    @staticmethod
    def compute_dual_gradient_energy(img: np.ndarray) -> np.ndarray:
        """
        Compute dual-gradient energy: sqrt((dI/dx)^2 + (dI/dy)^2).
        Complexity: O(H * W) = O(N^2) for an N x N image (visits each pixel once).
        """
        if HAS_NUMBA:
            return _fast_dual_gradient(img)

        img_f = img.astype(np.float64)
        h, w, _ = img_f.shape

        dx = np.zeros_like(img_f)
        dx[:, 1:-1, :] = (img_f[:, 2:, :] - img_f[:, :-2, :]) * 0.5
        dx[:, 0, :] = img_f[:, 1, :] - img_f[:, 0, :]
        dx[:, -1, :] = img_f[:, -1, :] - img_f[:, -2, :]

        dy = np.zeros_like(img_f)
        dy[1:-1, :, :] = (img_f[2:, :, :] - img_f[:-2, :, :]) * 0.5
        dy[0, :, :] = img_f[1, :, :] - img_f[0, :, :]
        dy[-1, :, :] = img_f[-1, :, :] - img_f[-2, :, :]

        energy_x = np.sum(dx ** 2, axis=2)
        energy_y = np.sum(dy ** 2, axis=2)
        return np.sqrt(energy_x + energy_y)

    def find_vertical_seam(self) -> np.ndarray:
        """
        Find minimal energy vertical seam via Dynamic Programming.
        Complexity: O(H * W) = O(N^2) for an N x N image.
        """
        energy = self.compute_dual_gradient_energy(self.current_image)

        if HAS_NUMBA:
            return _fast_find_seam(energy)

        # Vectorized DP fallback
        h, w = energy.shape
        dp = energy.copy()
        backtrack = np.zeros((h, w), dtype=np.int8)

        for i in range(1, h):
            prev = dp[i - 1]
            left = np.empty(w)
            left[0] = np.inf
            left[1:] = prev[:-1]

            right = np.empty(w)
            right[-1] = np.inf
            right[:-1] = prev[1:]

            stacked = np.stack([left, prev, right], axis=0)
            choice = np.argmin(stacked, axis=0)
            dp[i] += stacked[choice, np.arange(w)]
            backtrack[i] = choice - 1

        seam = np.empty(h, dtype=np.int32)
        seam[h - 1] = int(np.argmin(dp[h - 1]))
        for i in range(h - 2, -1, -1):
            seam[i] = seam[i + 1] + backtrack[i + 1, seam[i + 1]]

        return seam

    def remove_vertical_seam(self, seam: np.ndarray) -> None:
        h, w, c = self.current_image.shape
        rows = np.arange(h)

        removed_orig_indices = self.original_coords[rows, seam]
        self.seam_mask.flat[removed_orig_indices] = True
        self.seam_order_mask.flat[removed_orig_indices] = self.seams_removed_count
        self.seams_removed_count += 1

        keep_mask = np.ones((h, w), dtype=bool)
        keep_mask[rows, seam] = False

        self.current_image = self.current_image[keep_mask].reshape((h, w - 1, c))
        self.original_coords = self.original_coords[keep_mask].reshape((h, w - 1))

    def remove_horizontal_seam(self) -> None:
        self.current_image = np.transpose(self.current_image, (1, 0, 2))
        self.original_coords = np.transpose(self.original_coords, (1, 0))

        seam = self.find_vertical_seam()
        self.remove_vertical_seam(seam)

        self.current_image = np.transpose(self.current_image, (1, 0, 2))
        self.original_coords = np.transpose(self.original_coords, (1, 0))

    def reset(self) -> None:
        """Reset the working state back to the pristine original image."""
        self.current_image = self.original_image.copy()
        h, w, _ = self.original_image.shape
        self.original_coords = np.arange(h * w).reshape((h, w))
        self.seam_mask = np.zeros((h, w), dtype=bool)
        self.seam_order_mask = np.full((h, w), -1, dtype=np.int32)
        self.seams_removed_count = 0

    def resize(self, target_width: int, target_height: int, reset_first: bool = True) -> CarveMetrics:
        """
        Resize image to target_width x target_height.
        By default (reset_first=True), carving is always performed relative to the pristine
        original image, preventing cumulative distortion and dimension errors on repetitive calls.
        Seam removals are proportionally interleaved to preserve visual geometry.
        """
        if reset_first:
            self.reset()

        t_start = time.perf_counter()
        orig_h, orig_w, _ = self.original_image.shape

        if target_width > orig_w or target_height > orig_h:
            raise ValueError(
                f"Target size ({target_width}x{target_height}) cannot exceed original ({orig_w}x{orig_h})."
            )

        num_vertical = orig_w - target_width
        num_horizontal = orig_h - target_height

        initial_energy = self.compute_dual_gradient_energy(self.original_image)
        init_avg_energy = float(np.mean(initial_energy))

        # Proportionally interleave vertical and horizontal seam removals
        # to preserve aspect ratio uniformity and eliminate cross-seam artifacts
        v_rem = num_vertical
        h_rem = num_horizontal
        while v_rem > 0 or h_rem > 0:
            if v_rem > 0 and h_rem > 0:
                if (v_rem / num_vertical) >= (h_rem / num_horizontal):
                    seam = self.find_vertical_seam()
                    self.remove_vertical_seam(seam)
                    v_rem -= 1
                else:
                    self.remove_horizontal_seam()
                    h_rem -= 1
            elif v_rem > 0:
                seam = self.find_vertical_seam()
                self.remove_vertical_seam(seam)
                v_rem -= 1
            else:
                self.remove_horizontal_seam()
                h_rem -= 1

        t_elapsed = time.perf_counter() - t_start

        final_energy = self.compute_dual_gradient_energy(self.current_image)
        final_avg_energy = float(np.mean(final_energy))

        orig_buf = io.BytesIO()
        Image.fromarray(self.original_image).save(orig_buf, format="PNG", optimize=True)
        orig_bytes = orig_buf.tell()

        comp_buf = io.BytesIO()
        Image.fromarray(self.current_image).save(comp_buf, format="PNG", optimize=True)
        comp_bytes = comp_buf.tell()

        total_seams = num_vertical + num_horizontal
        orig_pixels = orig_w * orig_h
        new_pixels = target_width * target_height
        pixels_removed = orig_pixels - new_pixels
        pixel_reduction_pct = (pixels_removed / orig_pixels) * 100.0 if orig_pixels > 0 else 0.0
        byte_ratio = (comp_bytes / orig_bytes) * 100.0 if orig_bytes > 0 else 100.0
        seams_per_sec = (total_seams / t_elapsed) if t_elapsed > 0 else 0.0
        energy_change_pct = (
            ((final_avg_energy - init_avg_energy) / init_avg_energy) * 100.0
            if init_avg_energy > 0
            else 0.0
        )

        return CarveMetrics(
            original_width=orig_w,
            original_height=orig_h,
            compressed_width=target_width,
            compressed_height=target_height,
            vertical_seams_removed=num_vertical,
            horizontal_seams_removed=num_horizontal,
            total_pixels_removed=pixels_removed,
            pixel_reduction_percent=round(pixel_reduction_pct, 2),
            original_bytes_png=orig_bytes,
            compressed_bytes_png=comp_bytes,
            byte_compression_ratio=round(byte_ratio, 2),
            total_time_seconds=round(t_elapsed, 4),
            seams_per_second=round(seams_per_sec, 2),
            initial_average_energy=round(init_avg_energy, 2),
            final_average_energy=round(final_avg_energy, 2),
            energy_density_change_percent=round(energy_change_pct, 2),
            energy_method=self.energy_method,
        )

    def get_seam_visualization(self) -> np.ndarray:
        h, w, _ = self.original_image.shape
        vis = self.original_image.copy()
        if self.seams_removed_count == 0:
            return vis

        norm_order = self.seam_order_mask.astype(np.float64) / max(1, self.seams_removed_count - 1)
        r = np.full((h, w), 255, dtype=np.uint8)
        g = np.clip(30 + norm_order * 180, 0, 255).astype(np.uint8)
        b = np.full((h, w), 40, dtype=np.uint8)

        seam_pixels = self.seam_mask
        vis[seam_pixels, 0] = r[seam_pixels]
        vis[seam_pixels, 1] = g[seam_pixels]
        vis[seam_pixels, 2] = b[seam_pixels]
        return vis

    def get_energy_map_image(self, target: str = "original") -> np.ndarray:
        img = self.original_image if target == "original" else self.current_image
        energy = self.compute_dual_gradient_energy(img)

        p99 = np.percentile(energy, 99)
        norm_e = np.clip(energy / (p99 if p99 > 0 else 1.0), 0.0, 1.0)

        h, w = norm_e.shape
        heatmap = np.zeros((h, w, 3), dtype=np.uint8)

        m1 = norm_e <= 0.35
        t1 = np.where(m1, norm_e / 0.35, 0)
        heatmap[m1, 0] = np.clip(15 + t1[m1] * 105, 0, 255).astype(np.uint8)
        heatmap[m1, 1] = np.clip(20 + t1[m1] * 8, 0, 255).astype(np.uint8)
        heatmap[m1, 2] = np.clip(60 + t1[m1] * 80, 0, 255).astype(np.uint8)

        m2 = (norm_e > 0.35) & (norm_e <= 0.7)
        t2 = np.where(m2, (norm_e - 0.35) / 0.35, 0)
        heatmap[m2, 0] = np.clip(120 + t2[m2] * 120, 0, 255).astype(np.uint8)
        heatmap[m2, 1] = np.clip(28 + t2[m2] * 62, 0, 255).astype(np.uint8)
        heatmap[m2, 2] = np.clip(140 - t2[m2] * 110, 0, 255).astype(np.uint8)

        m3 = norm_e > 0.7
        t3 = np.where(m3, (norm_e - 0.7) / 0.3, 0)
        heatmap[m3, 0] = np.clip(240 + t3[m3] * 15, 0, 255).astype(np.uint8)
        heatmap[m3, 1] = np.clip(90 + t3[m3] * 145, 0, 255).astype(np.uint8)
        heatmap[m3, 2] = np.clip(30 + t3[m3] * 40, 0, 255).astype(np.uint8)

        return heatmap
