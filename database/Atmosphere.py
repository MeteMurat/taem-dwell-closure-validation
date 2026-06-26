# -*- coding: utf-8 -*-
"""database/Atmosphere.py (overflow-safe)

This is a drop-in replacement for your current database/Atmosphere.py.

Fix:
- Prevent FloatingPointError: overflow encountered in exp

Why it happens:
- rho(h) uses exp(-h*0.00015). If h becomes a large negative number (e.g.,
  due to a numerical overshoot), the exponent becomes a large positive number
  and exp(...) overflows.

Numerical policy:
- If h is not finite -> return 0.0 (vacuum)
- If h < 0 -> clamp to sea level (h=0)
- If h is very large (>200 km) -> return 0.0 (vacuum)
"""

import os
import numpy as np
from utils.interpolate import Interp1


class AtmosphereISA:
    def __init__(self):
        self.ISA = np.genfromtxt(os.path.dirname(__file__) + "/ISA.txt")
        self.T_h, self.rho_h, self.a_h = (
            Interp1(self.ISA[:, 0] * 1e3, self.ISA[:, i + 1]).pre for i in range(3)
        )

    def T(self, h):
        return self.T_h(h)

    def rho(self, h):
        """Density (kg/m^3) with overflow protection."""
        try:
            h = float(h)
        except Exception:
            return 0.0

        if not np.isfinite(h):
            return 0.0

        # Clamp altitude to physically meaningful range
        if h < 0.0:
            h = 0.0
        if h > 2.0e5:
            return 0.0

        # exp argument is <= 0 after clamp, but clip anyway for extra safety
        x = -h * 0.00015
        x = float(np.clip(x, -750.0, 50.0))
        return 1.225 * np.exp(x)

    def a(self, h):
        return self.a_h(h)


atmosphereISA = AtmosphereISA()


if __name__ == '__main__':
    a = AtmosphereISA()
    print(a.rho(2.5e4))
