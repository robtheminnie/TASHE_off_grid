"""
plot_deltaec_phases.py
----------------------
Reads a DeltaEC .sp file and plots Ph(p1) and Ph(U1) vs x,
one figure per leg, with segment number annotations.
Active acoustic power Edot = 0.5 * Re{p1 * conj(U1)} and reactive
acoustic power Qdot = 0.5 * Im{p1 * conj(U1)} are plotted on a
secondary y-axis.

DeltaEC convention note:
  In a TBRANCH, the branch leg velocity U is written with the positive
  direction pointing AWAY from the junction (into the branch). The trunk
  velocity is positive pointing AWAY from the junction along the trunk.
  Pressure is the same on all legs at the junction.

  To make the branch Ph(U1) visually consistent with the trunk convention
  (where positive U flows through the junction in the loop direction),
  180 deg is added to Ph(U1) for all branch legs (leg > 0). Ph(p1) is
  left unchanged as it is already in the same reference frame.

  Edot and Qdot have the same sign-flip applied for branch legs
  (multiplied by -1) so that positive Edot indicates power flow in
  the loop direction.

Usage:
    python plot_deltaec_phases.py <file.sp>
"""

import sys
import re
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict


# ---------------------------------------------------------------------------

def parse_sp_file(filepath):
    """Parse DeltaEC .sp file. Returns list of row dicts."""
    data_re = re.compile(
        r'^\s*(\d+):\s*(\d+)\s+'   # leg : seg
        r'(\S+)\s+'                 # x
        r'\S+\s+\S+\s+'            # GasA, Tm  (skip)
        r'(\S+)\s+(\S+)\s+'        # Re[p], Im[p]
        r'(\S+)\s+(\S+)'           # Re[U], Im[U]
    )
    rows = []
    with open(filepath, 'r') as f:
        for line in f:
            m = data_re.match(line)
            if m:
                try:
                    re_p = float(m.group(4))
                    im_p = float(m.group(5))
                    re_U = float(m.group(6))
                    im_U = float(m.group(7))
                    # Edot (active)   = 0.5 * Re{p1 * conj(U1)}
                    #                 = 0.5 * (Re[p]*Re[U] + Im[p]*Im[U])
                    # Qdot (reactive) = 0.5 * Im{p1 * conj(U1)}
                    #                 = 0.5 * (Im[p]*Re[U] - Re[p]*Im[U])
                    edot = 0.5 * (re_p * re_U + im_p * im_U)
                    qdot = 0.5 * (im_p * re_U - re_p * im_U)
                    rows.append(dict(
                        leg  = int(m.group(1)),
                        seg  = int(m.group(2)),
                        x    = float(m.group(3)),
                        ph_p = np.degrees(np.arctan2(im_p, re_p)),
                        ph_U = np.degrees(np.arctan2(im_U, re_U)),
                        edot = edot,
                        qdot = qdot,
                    ))
                except ValueError:
                    pass
    return rows


def apply_branch_correction(legs_dict):
    """
    Add 180 deg to Ph(U1) and flip sign of Edot for branch legs (leg > 0).

    In DeltaEC's .sp output, branch leg velocities point away from the
    junction. Adding 180 deg inverts the sign convention to match the
    trunk, making phase plots directly comparable at the junction.
    Ph(p1) is identical at the junction and needs no correction.

    Edot = 0.5 Re{p U*} and Qdot = 0.5 Im{p U*} are both linear in U,
    so the U sign-flip propagates directly: Edot/Qdot_corrected =
    -Edot/Qdot_raw on branch legs. This makes positive Edot mean power
    flowing in the loop direction on every leg.

    Result is wrapped to (-180, 180].
    """
    for leg_num, rows in legs_dict.items():
        if leg_num > 0:
            for r in rows:
                r['ph_U'] = (r['ph_U']) % 360.0 - 180.0
                r['edot'] = -r['edot']
                r['qdot'] = -r['qdot']
    return legs_dict


def seg_boundaries(leg_rows):
    """
    Return list of (seg_number, x_start) sorted by x, one entry per
    segment (first occurrence).
    """
    seen = {}
    for r in leg_rows:
        if r['seg'] not in seen:
            seen[r['seg']] = r['x']
    return sorted(seen.items(), key=lambda kv: kv[1])


# ---------------------------------------------------------------------------

def plot_leg(ax, leg_rows, leg_num):
    x    = np.array([r['x']    for r in leg_rows])
    ph_p = np.array([r['ph_p'] for r in leg_rows])
    ph_U = np.array([r['ph_U'] for r in leg_rows])
    edot = np.array([r['edot'] for r in leg_rows])
    qdot = np.array([r['qdot'] for r in leg_rows])
    ph_diff = ph_p - ph_U

    branch_note = '  [branch: Ph(U1) +180°, Edot/Qdot sign-flipped]' if leg_num > 0 else ''

    # --- left axis: phases ---
    l1, = ax.plot(x, ph_p, color='#CC3311', lw=2.0, label='Ph(p1)',  zorder=3)
    l2, = ax.plot(x, ph_U, color='#0077BB', lw=2.0, linestyle='--',
                  label='Ph(U1)', zorder=3)
    l3, = ax.plot(x, ph_diff, color='#009988', lw=2.0, linestyle=':',
                  label='Ph(p1) - Ph(U1)', zorder=3)
    ax.axhline(0, color='k', lw=0.5, linestyle=':')

    # --- right axis: acoustic power (active and reactive) ---
    ax2 = ax.twinx()
    l4, = ax2.plot(x, edot, color='#EE7733', lw=2.0, linestyle='-',
                   label='Edot active (W)', zorder=3, alpha=0.85)
    l5, = ax2.plot(x, qdot, color='#AA3377', lw=2.0, linestyle='-.',
                   label='Qdot reactive (W)', zorder=3, alpha=0.85)
    ax2.axhline(0, color='#888888', lw=0.4, linestyle=':', alpha=0.5)
    ax2.set_ylabel('Acoustic power  (W)', fontsize=10)

    # --- segment boundary annotations (use left axis for positioning) ---
    bounds = seg_boundaries(leg_rows)
    x_span = x[-1] - x[0] if x[-1] != x[0] else 1.0

    for seg, xb in bounds:
        ax.axvline(xb, color='#888888', lw=0.9, linestyle='--',
                   alpha=0.6, zorder=2)

    y_lo, y_hi = ax.get_ylim()
    y_range = y_hi - y_lo
    tier_y = [y_lo + 0.08 * y_range,
              y_lo + 0.22 * y_range]

    min_gap_frac = 0.06
    prev_x = -np.inf
    tier   = 0
    for seg, xb in bounds:
        gap = (xb - prev_x) / x_span
        if gap < min_gap_frac:
            tier = (tier + 1) % len(tier_y)
        else:
            tier = 0

        ax.text(xb + x_span * 0.005, tier_y[tier],
                f'seg {seg}',
                fontsize=8, color='#333333', va='bottom', ha='left',
                bbox=dict(boxstyle='round,pad=0.15', fc='white',
                          ec='none', alpha=0.75),
                zorder=4)
        prev_x = xb

    ax.set_xlim(x[0], x[-1])
    ax.set_ylabel('Phase (deg)', fontsize=10)
    ax.set_xlabel('Position  x  (m)', fontsize=10)
    ax.set_title(f'Leg {leg_num}{branch_note}', fontsize=11)

    # Combined legend with all five series
    lines = [l1, l2, l3, l4, l5]
    labels = [ln.get_label() for ln in lines]
    ax.legend(lines, labels, loc='upper right', fontsize=9)

    ax.grid(True, alpha=0.25)


# ---------------------------------------------------------------------------

def print_junction_check(legs_dict):
    """Print phase and Edot values at TBRANCH junction for verification."""
    trunk = legs_dict.get(0, [])
    if not trunk:
        return
    for leg_num, rows in sorted(legs_dict.items()):
        if leg_num == 0 or not rows:
            continue
        x0 = rows[0]['x']
        trunk_pts = [r for r in trunk if abs(r['x'] - x0) < 1e-6]
        if not trunk_pts:
            continue
        t = trunk_pts[0]; b = rows[0]
        print(f"Junction (leg 0 vs leg {leg_num}) at x={x0:.4f} m:")
        print(f"  Trunk  Ph(p1)={t['ph_p']:+7.2f}°   Ph(U1)={t['ph_U']:+7.2f}°   "
              f"Edot={t['edot']:+8.3f} W   Qdot={t['qdot']:+8.3f} W")
        print(f"  Branch Ph(p1)={b['ph_p']:+7.2f}°   Ph(U1)={b['ph_U']:+7.2f}°   "
              f"Edot={b['edot']:+8.3f} W   Qdot={b['qdot']:+8.3f} W  [after sign corrections]")
        print(f"  Delta  Ph(p1)={b['ph_p']-t['ph_p']:+7.2f}°   "
              f"Ph(U1)={b['ph_U']-t['ph_U']:+7.2f}°   "
              f"dEdot={b['edot']-t['edot']:+8.3f} W   "
              f"dQdot={b['qdot']-t['qdot']:+8.3f} W")


# ---------------------------------------------------------------------------
def plot_phases(filepath=None, show=True):
    if filepath is None:
        if len(sys.argv) < 2:
            print("Usage: python plot_deltaec_phases.py <file.sp>")
            sys.exit(1)
        filepath = sys.argv[1]

    rows = parse_sp_file(filepath)
    if not rows:
        print(f"ERROR: no data rows found in {filepath}")
        sys.exit(1)

    legs = defaultdict(list)
    for r in rows:
        legs[r['leg']].append(r)

    legs = apply_branch_correction(legs)
    print_junction_check(legs)

    leg_numbers = sorted(legs.keys())
    n = len(leg_numbers)
    fig, axes = plt.subplots(n, 1, figsize=(12, 4.5 * n), squeeze=False)
    fig.suptitle(filepath, fontsize=10, y=1.005)

    for ax, leg_num in zip(axes[:, 0], leg_numbers):
        plot_leg(ax, legs[leg_num], leg_num)

    plt.tight_layout()
    out_path = filepath.replace('.sp', '_phases.png')
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"Saved: {out_path}")
    if show:
        plt.show()
    else:
        plt.close(fig)


if __name__ == '__main__':
    plot_phases()