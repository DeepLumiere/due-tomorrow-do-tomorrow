# Content-Aware Seam Carving: Mathematical Foundations & Code Implementation

This document provides a comprehensive, rigorous mathematical analysis of the Content-Aware Seam Carving algorithm alongside its exact Python and JavaScript implementations from `seam_carving.py`, `app.py`, and `index.html`. Every concept is illustrated with a concrete numerical example on a sample image matrix.

---

## Table of Contents
1. [Image Representation & Discrete Space](#1-image-representation--discrete-space)
2. [Dual-Gradient Energy Function ($e_1$)](#2-dual-gradient-energy-function-e_1)
3. [Seam Definition & Path Topology](#3-seam-definition--path-topology)
4. [Dynamic Programming Cumulative Minimum Energy ($M$)](#4-dynamic-programming-cumulative-minimum-energy-m)
5. [Backtracking & Seam Extraction](#5-backtracking--seam-extraction)
6. [Seam Removal & Coordinate Relabeling](#6-seam-removal--coordinate-relabeling)
7. [Horizontal Seam Carving via Transposition](#7-horizontal-seam-carving-via-transposition)
8. [Proportional Seam Interleaving](#8-proportional-seam-interleaving)
9. [Energy Landscape Normalization & Heatmap Mapping](#9-energy-landscape-normalization--heatmap-mapping)
10. [Analytical Metrics & Information Conservation](#10-analytical-metrics--information-conservation)
11. [Client-Side Aspect Ratio Locking](#11-client-side-aspect-ratio-locking)
12. [Complete Numerical Walkthrough on a $4 \times 5$ Image](#12-complete-numerical-walkthrough-on-a-4-times-5-image)

---

## 1. Image Representation & Discrete Space

An image is modeled as a discrete tensor mapping spatial pixel coordinates to 3-channel color intensities:

$$I: \{0, 1, \dots, H-1\} \times \{0, 1, \dots, W-1\} \to [0, 255]^3$$

Where:
- $H$: Image height (number of rows, indexed by $i$ or $y$).
- $W$: Image width (number of columns, indexed by $j$ or $x$).
- $c \in \{0, 1, 2\} \equiv \{R, G, B\}$: Color channels.

### Code Implementation (`seam_carving.py`)
```python
# Image ingested as NumPy 3D array of shape (H, W, 3) and uint8 dtype
self.original_image = np.array(image.convert("RGB"), dtype=np.uint8)
h, w, c = self.original_image.shape
```

---

## 2. Dual-Gradient Energy Function ($e_1$)

The energy function $E(i, j)$ assigns a scalar value representing the visual importance of pixel $(i, j)$. High energy corresponds to high-frequency edges and textures, whereas low energy indicates smooth, homogeneous regions.

### 2.1 Mathematical Formulation
For any pixel $(i, j)$ and color channel $c$:

#### Partial Derivative in $x$ (Horizontal Gradient):
$$\frac{\partial I_c(i, j)}{\partial x} \approx \begin{cases}
I_c(i, 1) - I_c(i, 0) & j = 0 \quad \text{(forward difference)} \\
\frac{I_c(i, j+1) - I_c(i, j-1)}{2} & 0 < j < W - 1 \quad \text{(central difference)} \\
I_c(i, W-1) - I_c(i, W-2) & j = W - 1 \quad \text{(backward difference)}
\end{cases}$$

#### Partial Derivative in $y$ (Vertical Gradient):
$$\frac{\partial I_c(i, j)}{\partial y} \approx \begin{cases}
I_c(1, j) - I_c(0, j) & i = 0 \quad \text{(forward difference)} \\
\frac{I_c(i+1, j) - I_c(i-1, j)}{2} & 0 < i < H - 1 \quad \text{(central difference)} \\
I_c(H-1, j) - I_c(H-2, j) & i = H - 1 \quad \text{(backward difference)}
\end{cases}$$

#### Multi-Channel Squared Gradient Magnitude:
$$\Delta_x^2(i, j) = \sum_{c \in \{R,G,B\}} \left(\frac{\partial I_c(i, j)}{\partial x}\right)^2$$
$$\Delta_y^2(i, j) = \sum_{c \in \{R,G,B\}} \left(\frac{\partial I_c(i, j)}{\partial y}\right)^2$$

#### Total Pixel Energy:
$$E(i, j) = \sqrt{\Delta_x^2(i, j) + \Delta_y^2(i, j)}$$

### 2.2 Side-by-Side: Math & Code Snippet
| Mathematical Operation | Python Implementation (`seam_carving.py`) |
| :--- | :--- |
| $\text{diff}_x = \frac{I(i, j+1) - I(i, j-1)}{2}$ | `diff_x = (float(img[i, j_next, ch]) - float(img[i, j_prev, ch])) * 0.5` |
| $\text{diff}_y = \frac{I(i+1, j) - I(i-1, j)}{2}$ | `diff_y = (float(img[i_next, j, ch]) - float(img[i_prev, j, ch])) * 0.5` |
| $\Delta_x^2 = \sum_c (\text{diff}_x)^2$ | `dx2 += diff_x * diff_x` |
| $\Delta_y^2 = \sum_c (\text{diff}_y)^2$ | `dy2 += diff_y * diff_y` |
| $E(i, j) = \sqrt{\Delta_x^2 + \Delta_y^2}$ | `energy[i, j] = np.sqrt(dx2 + dy2)` |

#### Full Numba JIT Function:
```python
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
```

---

## 3. Seam Definition & Path Topology

A vertical seam $\mathbf{s}$ is an 8-connected trajectory of pixels spanning from top row $0$ to bottom row $H-1$:

$$\mathbf{s} = \{(i, x(i))\}_{i=0}^{H-1} = \{(0, x(0)), (1, x(1)), \dots, (H-1, x(H-1))\}$$

Subject to the **spatial connectivity constraint**:
$$|x(i) - x(i-1)| \le 1 \quad \forall i \in \{1, \dots, H-1\}$$

This restricts step choices to:
$$\Delta x \in \{-1, 0, +1\} \implies x(i) \in \{x(i-1) - 1, \; x(i-1), \; x(i-1) + 1\}$$

The total energy cost of seam $\mathbf{s}$ is:
$$E(\mathbf{s}) = \sum_{i=0}^{H-1} E(i, x(i))$$

The optimal vertical seam $\mathbf{s}^*$ minimizes total energy:
$$\mathbf{s}^* = \arg\min_{\mathbf{s}} E(\mathbf{s}) = \arg\min_{\mathbf{s}} \sum_{i=0}^{H-1} E(i, x(i))$$

---

## 4. Dynamic Programming Cumulative Minimum Energy ($M$)

Evaluating all valid seams by brute force would require testing $W \cdot 3^{H-1}$ paths ($O(W \cdot 3^H)$ exponential time). Dynamic programming computes the global optimum in **$O(H \cdot W)$** polynomial time.

### 4.1 Recurrence Relation
Let $M(i, j)$ be the minimum cumulative energy among all valid seams reaching pixel $(i, j)$:

#### Base Case (Row 0):
$$M(0, j) = E(0, j) \quad \forall j \in \{0, 1, \dots, W-1\}$$

#### Inductive Step (Rows $i = 1, \dots, H-1$):
$$M(i, j) = E(i, j) + \min \begin{cases}
M(i-1, j-1) & \text{if } j > 0 \\
M(i-1, j) \\
M(i-1, j+1) & \text{if } j < W - 1
\end{cases}$$

With boundary condition:
$$M(i-1, -1) = \infty, \quad M(i-1, W) = \infty$$

### 4.2 Backtrack Matrix
To reconstruct the seam, record the chosen horizontal offset:
$$\text{backtrack}(i, j) = \arg\min_{k \in \{-1, 0, 1\}} M(i-1, j+k)$$

### 4.3 Side-by-Side: Math & Code Snippet
| Math DP Recurrence | Python Implementation (`seam_carving.py`) |
| :--- | :--- |
| $\text{best} = M(i-1, j)$ | `best = dp[i - 1, j]; choice = 0` |
| $\text{if } M(i-1, j-1) < \text{best}$ | `if j > 0 and dp[i - 1, j - 1] < best: best = dp[i - 1, j - 1]; choice = -1` |
| $\text{if } M(i-1, j+1) < \text{best}$ | `if j < w - 1 and dp[i - 1, j + 1] < best: best = dp[i - 1, j + 1]; choice = 1` |
| $M(i, j) = E(i, j) + \text{best}$ | `dp[i, j] += best` |
| $\text{backtrack}(i, j) = \text{choice}$ | `backtrack[i, j] = choice` |

---

## 5. Backtracking & Seam Extraction

Once row $H-1$ is reached, the minimum total seam energy is:
$$E^* = \min_{j \in \{0, \dots, W-1\}} M(H-1, j)$$

### 5.1 Endpoint Selection:
$$x(H-1) = \arg\min_{j \in \{0, \dots, W-1\}} M(H-1, j)$$

### 5.2 Reverse Traversal:
For $i = H-2, H-3, \dots, 0$:
$$x(i) = x(i+1) + \text{backtrack}(i+1, x(i+1))$$

```python
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
```

---

## 6. Seam Removal & Coordinate Relabeling

Removing vertical seam $\mathbf{s}^*$ transforms image dimension:
$$\mathbb{R}^{H \times W \times 3} \longrightarrow \mathbb{R}^{H \times (W-1) \times 3}$$

For each row $i \in \{0, \dots, H-1\}$:
$$I_{\text{new}}(i, j, c) = \begin{cases}
I(i, j, c) & 0 \le j < x(i) \\
I(i, j+1, c) & x(i) \le j < W - 1
\end{cases}$$

### Boolean Masking Implementation:
```python
def remove_vertical_seam(self, seam: np.ndarray) -> None:
    h, w, c = self.current_image.shape
    rows = np.arange(h)

    # Track coordinate history in original unreduced image
    removed_orig_indices = self.original_coords[rows, seam]
    self.seam_mask.flat[removed_orig_indices] = True
    self.seam_order_mask.flat[removed_orig_indices] = self.seams_removed_count
    self.seams_removed_count += 1

    # Create 2D keep-mask
    keep_mask = np.ones((h, w), dtype=bool)
    keep_mask[rows, seam] = False

    # Extract retained pixels and reshape to (H, W - 1, C)
    self.current_image = self.current_image[keep_mask].reshape((h, w - 1, c))
    self.original_coords = self.original_coords[keep_mask].reshape((h, w - 1))
```

---

## 7. Horizontal Seam Carving via Transposition

A horizontal seam is an 8-connected path from left to right:
$$\mathbf{s}_h = \{(y(j), j)\}_{j=0}^{W-1} \quad \text{with } |y(j) - y(j-1)| \le 1$$

Rather than rewriting a horizontal DP algorithm, matrix transposition reduces the problem directly to the vertical formulation:

$$I^T(j, i, c) = I(i, j, c) \quad \text{where } I \in \mathbb{R}^{H \times W \times C} \implies I^T \in \mathbb{R}^{W \times H \times C}$$

$$\mathbf{s}_{\text{horizontal}}(I) \equiv \mathbf{s}_{\text{vertical}}(I^T)$$

```python
def remove_horizontal_seam(self) -> None:
    # Transpose H x W -> W x H
    self.current_image = np.transpose(self.current_image, (1, 0, 2))
    self.original_coords = np.transpose(self.original_coords, (1, 0))

    # Find and remove vertical seam on transposed matrix
    seam = self.find_vertical_seam()
    self.remove_vertical_seam(seam)

    # Transpose back: (W - 1) x H -> H x (W - 1) -> (H - 1) x W
    self.current_image = np.transpose(self.current_image, (1, 0, 2))
    self.original_coords = np.transpose(self.original_coords, (1, 0))
```

---

## 8. Proportional Seam Interleaving

When shrinking both width ($N_v$ vertical seams) and height ($N_h$ horizontal seams), removing all vertical seams first before horizontal seams creates directional stretching and orthogonal step artifacts.

The algorithm dynamically balances removal to preserve aspect ratio uniformly:

$$\text{Remaining fractions: } f_v = \frac{v_{\text{rem}}}{N_v}, \quad f_h = \frac{h_{\text{rem}}}{N_h}$$

$$\text{Decision Rule: } \begin{cases}
\text{Remove vertical seam} & \text{if } f_v \ge f_h \\
\text{Remove horizontal seam} & \text{if } f_v < f_h
\end{cases}$$

```python
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
```

---

## 9. Energy Landscape Normalization & Heatmap Mapping

Due to sharp edges, raw energy $E(i, j)$ has extreme dynamic range. Standard min-max normalization crushes subtle gradient differences. The codebase applies **99th-percentile robust normalization**:

$$p_{99} = \text{percentile}(E, 99)$$
$$\hat{E}(i, j) = \min\left(1.0, \; \frac{E(i, j)}{\max(1.0, p_{99})}\right)$$

### Piecewise Linear Colormap:
The normalized scalar $\hat{E} \in [0, 1]$ maps into RGB space across three color zones:
$$\text{Color}(\hat{E}) = \begin{cases}
\text{Deep Violet} \to \text{Purple} & \hat{E} \in [0.0, 0.35] \\
\text{Purple} \to \text{Amber} & \hat{E} \in (0.35, 0.70] \\
\text{Amber} \to \text{Bright Gold/White} & \hat{E} \in (0.70, 1.0]
\end{cases}$$

```python
p99 = np.percentile(energy, 99)
norm_e = np.clip(energy / (p99 if p99 > 0 else 1.0), 0.0, 1.0)

# Segment 1: [0.00, 0.35]
m1 = norm_e <= 0.35
t1 = np.where(m1, norm_e / 0.35, 0)
heatmap[m1, 0] = np.clip(15 + t1[m1] * 105, 0, 255).astype(np.uint8)
heatmap[m1, 1] = np.clip(20 + t1[m1] * 8, 0, 255).astype(np.uint8)
heatmap[m1, 2] = np.clip(60 + t1[m1] * 80, 0, 255).astype(np.uint8)
```

---

## 10. Analytical Metrics & Information Conservation

### 10.1 Pixel Reduction Ratio
$$\Delta_{\text{pixels}} = \frac{W_{\text{orig}} \cdot H_{\text{orig}} - W_{\text{new}} \cdot H_{\text{new}}}{W_{\text{orig}} \cdot H_{\text{orig}}} \times 100\%$$

### 10.2 File Byte Compression Ratio
$$R_{\text{bytes}} = \frac{\text{Bytes}_{\text{compressed}}}{\text{Bytes}_{\text{original}}} \times 100\%$$

### 10.3 Average Energy Density Change
$$\bar{E} = \frac{1}{H \cdot W} \sum_{i=0}^{H-1} \sum_{j=0}^{W-1} E(i, j)$$
$$\Delta \bar{E} = \left(\frac{\bar{E}_{\text{final}} - \bar{E}_{\text{initial}}}{\bar{E}_{\text{initial}}}\right) \times 100\%$$

> **Theoretical Significance**: In content-aware resizing, $\Delta \bar{E} > 0$ validates that low-energy pixels were preferentially purged, concentrating the remaining image energy density on salient features.

---

## 11. Client-Side Aspect Ratio Locking

Implemented in `index.html`, this preserves aspect ratio $\rho = \frac{W_{\text{orig}}}{H_{\text{orig}}}$ when resizing:

$$W_{\text{target}} = W_{\text{orig}} - \Delta v$$
$$H_{\text{target}} = \text{round}\left(W_{\text{target}} \cdot \frac{H_{\text{orig}}}{W_{\text{orig}}}\right)$$
$$\Delta h = \max\left(0, \; H_{\text{orig}} - H_{\text{target}}\right)$$

```javascript
function syncRatioFromWidth() {
  const v = parseInt(document.getElementById('inputSeamsV').value) || 0;
  const newW = originalWidth - v;
  const targetH = Math.round(newW * (originalHeight / originalWidth));
  const newH = Math.max(0, originalHeight - targetH);
  const inputH = document.getElementById('inputSeamsH');
  inputH.value = Math.min(inputH.max, Math.max(0, newH));
  updateSliderLabels();
}
```

---

## 12. Complete Numerical Walkthrough on a $4 \times 5$ Image

To see all equations in action, consider a grayscale image ($C=1$) of size $4 \times 5$ ($H=4$ rows, $W=5$ columns):

### 12.1 Input Pixel Matrix $I(i, j)$
$$I = \begin{bmatrix}
100 & 100 & 100 & 100 & 100 \\
100 & 200 & 200 & 200 & 100 \\
100 & 200 & 255 & 200 & 100 \\
100 & 100 & 100 & 100 & 100
\end{bmatrix}$$

---

### 12.2 Gradient & Energy Matrix $E(i, j)$
Using central differences $\frac{\partial I(i,j)}{\partial x} = \frac{I(i, j+1) - I(i, j-1)}{2}$ and clamping at boundaries:

- For interior pixel $(1, 1)$ ($I=200$):
  - $\frac{\partial I}{\partial x} = \frac{I(1, 2) - I(1, 0)}{2} = \frac{200 - 100}{2} = 50.0$
  - $\frac{\partial I}{\partial y} = \frac{I(2, 1) - I(0, 1)}{2} = \frac{200 - 100}{2} = 50.0$
  - $E(1, 1) = \sqrt{50.0^2 + 50.0^2} = \sqrt{2500 + 2500} \approx \mathbf{70.71}$

- For pixel $(0, 0)$ (Top-left corner, forward difference):
  - $\frac{\partial I}{\partial x} = I(0, 1) - I(0, 0) = 100 - 100 = 0$
  - $\frac{\partial I}{\partial y} = I(1, 0) - I(0, 0) = 100 - 100 = 0$
  - $E(0, 0) = \mathbf{0.0}$

- For pixel $(2, 2)$ ($I=255$, center peak):
  - $\frac{\partial I}{\partial x} = \frac{I(2, 3) - I(2, 1)}{2} = \frac{200 - 200}{2} = 0.0$
  - $\frac{\partial I}{\partial y} = \frac{I(3, 2) - I(1, 2)}{2} = \frac{100 - 200}{2} = -50.0$
  - $E(2, 2) = \sqrt{0^2 + (-50)^2} = \mathbf{50.00}$

Computing for all coordinates yields the Energy Matrix $E$:

$$E \approx \begin{bmatrix}
0.0 & 50.0 & 50.0 & 50.0 & 0.0 \\
50.0 & 70.71 & 27.50 & 70.71 & 50.0 \\
50.0 & 85.00 & 50.00 & 85.00 & 50.0 \\
0.0 & 50.0 & 77.50 & 50.0 & 0.0
\end{bmatrix}$$

---

### 12.3 DP Cumulative Minimum Energy Matrix $M(i, j)$

#### Row 0 (Base Case):
$$M(0, :) = [0.0, \; 50.0, \; 50.0, \; 50.0, \; 0.0]$$

#### Row 1:
- $M(1, 0) = E(1, 0) + \min(M(0, 0), M(0, 1)) = 50.0 + \min(0.0, 50.0) = \mathbf{50.0}$ (choice: $0$)
- $M(1, 1) = E(1, 1) + \min(M(0, 0), M(0, 1), M(0, 2)) = 70.71 + \min(0.0, 50.0, 50.0) = \mathbf{70.71}$ (choice: $-1$)
- $M(1, 2) = E(1, 2) + \min(M(0, 1), M(0, 2), M(0, 3)) = 27.50 + \min(50.0, 50.0, 50.0) = \mathbf{77.50}$ (choice: $0$)
- $M(1, 3) = E(1, 3) + \min(M(0, 2), M(0, 3), M(0, 4)) = 70.71 + \min(50.0, 50.0, 0.0) = \mathbf{70.71}$ (choice: $+1$)
- $M(1, 4) = E(1, 4) + \min(M(0, 3), M(0, 4)) = 50.0 + \min(50.0, 0.0) = \mathbf{50.0}$ (choice: $0$)

#### Row 2:
- $M(2, 0) = 50.0 + \min(50.0, 70.71) = \mathbf{100.0}$ (choice: $0$)
- $M(2, 1) = 85.0 + \min(50.0, 70.71, 77.5) = \mathbf{135.0}$ (choice: $-1$)
- $M(2, 2) = 50.0 + \min(70.71, 77.5, 70.71) = \mathbf{120.71}$ (choice: $-1$)
- $M(2, 3) = 85.0 + \min(77.5, 70.71, 50.0) = \mathbf{135.0}$ (choice: $+1$)
- $M(2, 4) = 50.0 + \min(70.71, 50.0) = \mathbf{100.0}$ (choice: $0$)

#### Row 3:
- $M(3, 0) = 0.0 + \min(100.0, 135.0) = \mathbf{100.0}$ (choice: $0$)
- $M(3, 1) = 50.0 + \min(100.0, 135.0, 120.71) = \mathbf{150.0}$ (choice: $-1$)
- $M(3, 2) = 77.5 + \min(135.0, 120.71, 135.0) = \mathbf{198.21}$ (choice: $0$)
- $M(3, 3) = 50.0 + \min(120.71, 135.0, 100.0) = \mathbf{150.0}$ (choice: $+1$)
- $M(3, 4) = 0.0 + \min(135.0, 100.0) = \mathbf{100.0}$ (choice: $0$)

Cumulative Energy Matrix $M$:
$$M = \begin{bmatrix}
0.0 & 50.0 & 50.0 & 50.0 & 0.0 \\
50.0 & 70.71 & 77.50 & 70.71 & 50.0 \\
100.0 & 135.0 & 120.71 & 135.0 & 100.0 \\
\mathbf{100.0} & 150.0 & 198.21 & 150.0 & \mathbf{100.0}
\end{bmatrix}$$

---

### 12.4 Seam Backtracking & Minimum Path
On the bottom row $i=3$, the minimum value is $100.0$ at column $j=0$ (or $j=4$).
Selecting index $x(3) = 0$:

1. $i = 3: \quad x(3) = 0$
2. $i = 2: \quad x(2) = x(3) + \text{backtrack}(3, 0) = 0 + 0 = \mathbf{0}$
3. $i = 1: \quad x(1) = x(2) + \text{backtrack}(2, 0) = 0 + 0 = \mathbf{0}$
4. $i = 0: \quad x(0) = x(1) + \text{backtrack}(1, 0) = 0 + 0 = \mathbf{0}$

The optimal seam is:
$$\mathbf{s}^* = \{(0, 0), \; (1, 0), \; (2, 0), \; (3, 0)\}$$
Total Seam Cost: $E(\mathbf{s}^*) = 0.0 + 50.0 + 50.0 + 0.0 = \mathbf{100.0}$.

---

### 12.5 Resulting Carved Image $I_{\text{new}}$ ($4 \times 4$)
Removing column $x(i)$ from each row:

$$I_{\text{new}} = \begin{bmatrix}
100 & 100 & 100 & 100 \\
200 & 200 & 200 & 100 \\
200 & 255 & 200 & 100 \\
100 & 100 & 100 & 100
\end{bmatrix}$$

Notice that the high-energy feature ($200, 255, 200$) was **completely preserved**, while the low-energy boundary was removed. This exemplifies the power of content-aware seam carving.
