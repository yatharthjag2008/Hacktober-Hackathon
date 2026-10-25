# Neon Runner

**Pitch**: A fast-paced 3D endless runner where a hover-bike dodges barriers and collects energy in a glowing cyberpunk city.

**2D or 3D**: 3D

**Core Loop**:
- Race forward automatically at increasing speed.
- Switch between 3 lanes to avoid obstacles.
- Collect energy orbs to increase score.
- Jump over low barriers.
- Survive as long as possible.

**Controls**:
- `A` / `Left Arrow`: Switch to left lane.
- `D` / `Right Arrow`: Switch to right lane.
- `Space`: Jump.
- `R`: Restart game.

**Win/Lose**:
- **Lose**: Collision with a barrier.
- **Win**: Endless (high score).

**Scoring and HUD**:
- **Score**: Based on distance and orbs collected.
- **HUD**: Top-left display showing Distance, Speed, and Score in neon colors.
- **Game Over**: Centered text with final score and "Press R to Restart".

**Look**:
- **Environment**: Dark background with thick fog.
- **Road**: Dark grey plane with glowing neon lane markers (Cyan/Pink).
- **Buildings**: Tall dark boxes with bright, colorful emissive strips (Pink, Cyan, Purple).
- **Player**: A sleek, glowing hover-bike (composed of basic primitives).
- **Obstacles**: Glowing red cubes.
- **Orbs**: Glowing yellow spheres.
- **Camera**: Third-person chase camera following the bike.

**Out of Scope**:
- Complex physics/drifting.
- Music/Sound effects.
- Multiple bike models.
- Destructible environments.
