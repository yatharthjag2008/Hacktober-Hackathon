# Injected by the Harness during a Visual Check only. Saves screenshots of the running
# game at fixed frames into $HARNESS_SHOT_DIR, then quits.
extends Node

const SHOT_FRAMES := [60, 240]

var _frame := 0

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS

func _process(_delta: float) -> void:
	_frame += 1
	if _frame in SHOT_FRAMES:
		var dir := OS.get_environment("HARNESS_SHOT_DIR")
		get_viewport().get_texture().get_image().save_png("%s/shot_%d.png" % [dir, _frame])
	if _frame >= SHOT_FRAMES.back():
		get_tree().quit()
