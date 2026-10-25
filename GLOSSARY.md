# Glossary

**Harness**
The open-source agent loop (prompts, tools and control flow) that drives any language model to build a Godot game from a Game Brief. It is model-agnostic: it works with any model, including open-weight ones.
_Avoid_: framework, wrapper, MCP server (a tool layer for someone else's agent is a different thing)

**Game Brief**
The plain-language description of a game that a Player-Creator gives the Harness.
_Avoid_: prompt, spec

**Player-Creator**
The person who writes a Game Brief and receives a playable Godot project. They are not assumed to know Godot.
_Avoid_: developer, user (too vague)

**Run Check**
A headless launch of the generated game whose errors are fed back to the model. A game is "done" only when a Run Check comes back clean.
_Avoid_: test, validation

**Design Interview**
The optional conversation before building, where the Harness asks the Player-Creator about the game's design in rounds, with a recommended answer for each question, until they accept a Design Proposal.
_Avoid_: grilling (informal), questionnaire

**Design Proposal**
The written description of a game that the Player-Creator accepts after a Design Interview. Once accepted, it is the source of truth for what the game is, and it is updated as the game changes.
_Avoid_: spec, plan

**Change Request**
Anything the Player-Creator asks for after a game is built: a new feature, a change, or a bug they found while playing. Each one goes through the same Run Check before it is done.
_Avoid_: ticket, issue, prompt

**Visual Check**
After a clean Run Check, screenshots of the game actually rendering are shown to the model, which compares them with the Design Proposal and fixes what looks wrong.
_Avoid_: screenshot test
