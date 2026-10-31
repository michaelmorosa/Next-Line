// Jump and crash detection from the accelerometer. Pure functions of the samples, so they can be tested and tuned
// with logs from the Sensor Lab screen.
//
// The phone could be at any angle in a pocket or pack, so everything uses the total acceleration
// g = sqrt(x² + y² + z²) in units of g, never a direction. At rest g is 1. In free fall (in the air off a jump)
// it drops toward 0, and a landing or impact spikes it well above 1.

export const JUMP_DEFAULTS = {
  enterG: 0.4, // free fall starts below this
  exitG: 0.65, // ...and ends above this (the gap stops noise from ending it early)
  minAirS: 0.15, // shorter dips are the rider's own movement, not air
  maxAirS: 2.5,
  landingG: 1.6, // a real landing follows the free fall with a spike...
  landingWindowMs: 300, // ...this soon after
};

export const CRASH_DEFAULTS = {
  impactG: 4.5, // hard landings reach 3-4 g; crashes usually go higher
  settleMs: 2000, // ignore tumbling right after the impact
  stillMs: 8000, // then the phone has to stay still this long
  stillStdG: 0.08, // "still": g barely varies
  movingG: 2.0, // a spike like this during the still window means the rider is up and moving
};

export function magnitude(x, y, z) {
  return Math.sqrt(x * x + y * y + z * z);
}

// push(tMs, g, moving) returns { tMs, airtimeS } when a jump completes, otherwise null.
// `moving` should be false when GPS says the rider is stopped, so a phone dropped on the ground isn't a jump.
export function createJumpDetector(options = {}) {
  const o = { ...JUMP_DEFAULTS, ...options };
  let airStart = null;
  let pending = null; // free fall that ended, waiting for the landing spike

  return {
    push(tMs, g, moving = true) {
      if (pending) {
        if (g >= o.landingG) {
          const jump = pending;
          pending = null;
          return { tMs: jump.tMs, airtimeS: jump.airtimeS };
        }
        if (tMs - pending.endMs > o.landingWindowMs) pending = null;
        return null;
      }
      if (airStart === null) {
        if (moving && g < o.enterG) airStart = tMs;
        return null;
      }
      if (g >= o.exitG) {
        const airtimeS = (tMs - airStart) / 1000;
        if (airtimeS >= o.minAirS && airtimeS <= o.maxAirS) {
          pending = { tMs: airStart, airtimeS: Math.round(airtimeS * 100) / 100, endMs: tMs };
          // Landing spike can be this very sample.
          if (g >= o.landingG) {
            const jump = pending;
            pending = null;
            airStart = null;
            return { tMs: jump.tMs, airtimeS: jump.airtimeS };
          }
        }
        airStart = null;
      } else if ((tMs - airStart) / 1000 > o.maxAirS) {
        // Far too long to be air: the phone is lying on something soft, or sensor glitch.
        airStart = null;
      }
      return null;
    },
    reset() {
      airStart = null;
      pending = null;
    },
  };
}

// push(tMs, g, speed) returns { tMs } (the impact time) when a big impact is followed by stillness.
// `speed` is the latest GPS speed in m/s; riding on cancels.
export function createCrashDetector(options = {}) {
  const o = { ...CRASH_DEFAULTS, ...options };
  let impactMs = null;
  let n = 0;
  let sum = 0;
  let sumSq = 0;

  const clear = () => {
    impactMs = null;
    n = 0;
    sum = 0;
    sumSq = 0;
  };

  return {
    push(tMs, g, speed = 0) {
      if (impactMs === null) {
        if (g >= o.impactG) impactMs = tMs;
        return null;
      }
      const since = tMs - impactMs;
      if (since < o.settleMs) {
        if (g >= o.impactG) impactMs = tMs; // still tumbling: time from the last hit
        return null;
      }
      if (g >= o.movingG || speed > 3) {
        clear();
        return null;
      }
      n += 1;
      sum += g;
      sumSq += g * g;
      if (since >= o.settleMs + o.stillMs) {
        const mean = sum / n;
        const std = Math.sqrt(Math.max(0, sumSq / n - mean * mean));
        const event = std <= o.stillStdG ? { tMs: impactMs } : null;
        clear();
        return event;
      }
      return null;
    },
    reset: clear,
  };
}
