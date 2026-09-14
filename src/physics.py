"""Arcade car physics.

The model is intentionally simple but keeps the ingredients the brief asks for
clearly separated:

    * forward velocity   (along the car's nose)
    * lateral velocity   (sideways slide)
    * acceleration / brake / reverse
    * drag                (air resistance, ~v^2)
    * grip                (how quickly lateral velocity is killed)
    * steering            (speed dependent)

`simulate` mutates a car-like object exposing:
    pos (Vector2), velocity (Vector2), angle (degrees), plus the tuning
    attributes listed in settings.CARS and the transient ``surface`` string.
"""

from __future__ import annotations

import pygame

from .utils import clamp, sign

# surface -> (forward friction extra, grip multiplier, max-speed multiplier)
SURFACES = {
    "track": (0.0, 1.0, 1.0),
    "grass": (2.6, 0.42, 0.52),      # off-track: big speed loss, low grip, slides
    "kerb": (0.35, 0.86, 0.96),      # a rumble: small grip loss, small slow-down
}


def _surface_params(car):
    surf = getattr(car, "surface", "track")
    fric, grip, vmax = SURFACES.get(surf, SURFACES["track"])
    if surf == "grass":
        # rally-style cars cope far better off the tarmac
        off = clamp(getattr(car, "offroad_grip", 1.0), 0.5, 2.0)
        grip = clamp(grip * off, 0.0, 1.0)
        vmax = clamp(vmax * (1.0 + (off - 1.0) * 0.6), 0.0, 1.0)
        fric = fric / off
    return fric, grip, vmax


def steering_factor(speed: float, max_speed: float) -> float:
    """0 at standstill, ramps up quickly, stays high (twitchy) at top speed."""
    if speed < 4.0:
        return 0.0
    ramp = clamp(speed / 90.0, 0.0, 1.0)          # full authority by ~90 u/s
    # a touch more sensitive at the very top end -> harder to hold a line
    high = 1.0 + 0.22 * clamp((speed - 0.55 * max_speed) / (0.45 * max_speed), 0.0, 1.0)
    return ramp * high


def simulate(car, throttle: float, steer: float, handbrake: bool, dt: float,
             *, nitro: bool = False) -> dict:
    """Advance the car by ``dt`` seconds.  Returns a small telemetry dict."""
    forward = pygame.Vector2(1, 0).rotate(car.angle)
    right = pygame.Vector2(forward.y, -forward.x)

    vel_fwd = car.velocity.dot(forward)
    vel_lat = car.velocity.dot(right)

    surf_fric, surf_grip, surf_vmax = _surface_params(car)

    # --- engine / brake / reverse ------------------------------------- #
    power = car.engine_power * (car.nitro_power_mult if nitro else 1.0)
    max_speed = car.max_speed * (car.nitro_speed_mult if nitro else 1.0) * surf_vmax

    if throttle > 0.01:
        accel = throttle * power
    elif throttle < -0.01:
        if vel_fwd > 6.0:
            accel = throttle * car.brake_power          # braking
        else:
            accel = throttle * car.reverse_speed * 3.0  # reversing acceleration
    else:
        accel = 0.0

    vel_fwd += accel * dt

    # rolling resistance + engine braking when coasting
    if abs(throttle) < 0.01:
        vel_fwd = _move_to_zero(vel_fwd, 55.0 * dt)
    vel_fwd -= sign(vel_fwd) * vel_fwd * vel_fwd * car.drag * dt      # aero drag
    vel_fwd -= sign(vel_fwd) * surf_fric * 34.0 * dt                 # surface scrub

    lo = -car.reverse_speed
    vel_fwd = clamp(vel_fwd, lo, max_speed)

    # --- lateral grip ----------------------------------------------- #
    base_grip = car.drift_grip if handbrake else car.grip
    grip = base_grip * surf_grip
    # lateral friction proportional to how fast we're sliding, capped so it
    # never overshoots (which would look like a snap)
    grip_step = clamp(grip * dt, 0.0, 1.0)
    lost_lat = vel_lat * grip_step
    vel_lat -= lost_lat

    # tyre scrub: killing sideways speed costs a little forward speed, so hard
    # cornering (and especially fighting understeer) bleeds momentum.  During a
    # handbrake slide the scrub is much lower - you keep speed but slide wide.
    scrub = 0.05 if handbrake else 0.16
    vel_fwd -= sign(vel_fwd) * min(abs(vel_fwd), abs(lost_lat) * scrub)

    # --- steering --------------------------------------------------- #
    speed = car.velocity.length()
    sfac = steering_factor(speed, car.max_speed)
    direction = 1.0 if vel_fwd >= -2.0 else -1.0     # reversed steering in reverse
    turn = steer * car.steer_rate * sfac * direction
    if handbrake:
        turn *= 1.35                                  # easier to swing the tail
    car.angle = (car.angle + turn * dt) % 360.0

    # --- recompose ------------------------------------------------- #
    forward = pygame.Vector2(1, 0).rotate(car.angle)
    right = pygame.Vector2(forward.y, -forward.x)
    car.velocity = forward * vel_fwd + right * vel_lat
    car.pos += car.velocity * dt

    slip = abs(vel_lat)
    return {
        "vel_fwd": vel_fwd,
        "vel_lat": vel_lat,
        "speed": car.velocity.length(),
        "slip": slip,
        "drifting": slip > 55.0 or (handbrake and speed > 60.0),
        "braking": throttle < -0.05 and vel_fwd > 20.0,
    }


def _move_to_zero(value: float, amount: float) -> float:
    if value > 0:
        return max(0.0, value - amount)
    return min(0.0, value + amount)


def resolve_wall(car, normal, penetration):
    """Push the car back inside the corridor and give a solid physical response.

    ``normal`` points *inward* (toward the racing line).  We split the velocity
    into the part along the wall (kept, so you can scrape along it) and the part
    into the wall (removed, plus a small bounce).  Returns the impact speed for
    camera shake / sfx (0 for a gentle graze).
    """
    normal = pygame.Vector2(normal)
    if normal.length_squared() < 1e-6:
        return 0.0
    normal = normal.normalize()
    car.pos += normal * (penetration + 0.75)

    vn = car.velocity.dot(normal)              # <0 => heading into the wall
    v_normal = normal * vn
    v_tangent = car.velocity - v_normal

    impact = 0.0
    if vn < 0:
        impact = -vn
        # keep sliding along the wall, lose the into-wall component, small kick back
        car.velocity = v_tangent * 0.86 + normal * (impact * 0.22)
    else:
        car.velocity = v_tangent * 0.9 + v_normal
    return impact


def resolve_car_overlap(a, b, min_dist=34.0):
    """Very cheap circle separation so opponents don't stack on the player."""
    delta = a.pos - b.pos
    d = delta.length()
    if d <= 0.001:
        delta = pygame.Vector2(1, 0)
        d = 1.0
    if d < min_dist:
        push = (min_dist - d) * 0.5
        n = delta / d
        a.pos += n * push
        b.pos -= n * push
        # exchange a bit of momentum along the contact normal
        rel = (a.velocity - b.velocity).dot(n)
        if rel < 0:
            imp = n * rel * 0.5
            a.velocity -= imp
            b.velocity += imp
        return True
    return False
