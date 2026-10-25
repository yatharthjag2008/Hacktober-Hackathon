# Title: Tiny Pong AI

# Pitch
A classic 2D arcade pong match against a fallible AI opponent.

# 2D or 3D
2D

# Core Loop
1. Ball bounces between player and AI.
2. Player moves their paddle to prevent the ball from crossing their goal line.
3. If the ball passes a paddle, the opposing side scores a point.
4. The loop repeats until a player reaches the score limit.

# Controls
- **Up Arrow / W**: Move paddle up.
- **Down Arrow / S**: Move paddle down.
- **R**: Restart game.

# Win/Lose
- **Win**: Be the first player to reach 5 points.
- **Lose**: Let the AI reach 5 points first.
- A simple on-screen text notification will announce the winner.

# Scoring and HUD
- **Score**: Two numbers displayed at the top of the screen (Player vs AI).
- **Rally Counter**: Displays the number of consecutive paddle hits in the current round.
- **HUD**: Simple text labels for the score, rally count, and a "Victory/Defeat" overlay at the end.

# Look
- **Visuals**: Minimalist geometric style.
- **Player/AI**: White rectangles.
- **Ball**: Red square.
- **Background**: Solid black.

# Out of Scope
- Audio/Sound effects.
- Menu screens (game starts immediately).
- Advanced physics (e.g., ball spin or varying speeds).
- Custom asset imports.
