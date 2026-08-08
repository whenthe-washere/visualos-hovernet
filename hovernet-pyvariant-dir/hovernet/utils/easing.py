"""Shared easing helpers for HoverNet animations.

The app's "fluid" feel everywhere uses a linear combined with ease shape:
- linear_out: linear for the first half, ease-out for the second (enters,
  resizes, preview transitions, sidebar text).
- linear_in:  ease-in for the first half, linear for the second (exits).
- smoothstep: slight ease-in followed by ease-out (sidebar background).
"""
from PySide6.QtCore import QEasingCurve


def _clamp(x):
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else x)


def _out_cubic(x):
    x = _clamp(x)
    return 1.0 - (1.0 - x) ** 3


def _in_cubic(x):
    x = _clamp(x)
    return x ** 3


def linear_out(x):
    """Linear until halfway, then ease-out to the end."""
    x = _clamp(x)
    if x < 0.5:
        return x
    return 0.5 + 0.5 * _out_cubic((x - 0.5) * 2.0)


def linear_in(x):
    """Ease-in for the first half, then linear to the end."""
    x = _clamp(x)
    if x < 0.5:
        return 0.5 * _in_cubic(x * 2.0)
    return x


def smoothstep(x):
    """Slight ease-in then ease-out (smoothstep)."""
    x = _clamp(x)
    return x * x * (3.0 - 2.0 * x)


def _make_curve(func):
    curve = QEasingCurve(QEasingCurve.Type.Custom)
    curve.setCustomType(func)
    return curve


# Curves are cached: QEasingCurve stores a reference to the Python custom
# callback, so the curve object must outlive any animation that uses it.
_CURVE_LINEAR_OUT = _make_curve(linear_out)
_CURVE_LINEAR_IN = _make_curve(linear_in)
_CURVE_SMOOTHSTEP = _make_curve(smoothstep)


def curve_linear_out():
    return _CURVE_LINEAR_OUT


def curve_linear_in():
    return _CURVE_LINEAR_IN


def curve_smoothstep():
    return _CURVE_SMOOTHSTEP
