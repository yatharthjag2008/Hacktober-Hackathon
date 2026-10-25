# Injected by the Harness during a Run Check only. Presses random keys and clicks
# so gameplay code paths (collisions, scoring, restarts) run and can surface errors.
extends Node

const KEYS := [KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_W, KEY_A, KEY_S, KEY_D,
	KEY_SPACE, KEY_ENTER, KEY_R]

var _rng := RandomNumberGenerator.new()
var _held: Array[int] = []
var _frame := 0

func _ready() -> void:
	_rng.seed = 1234
	process_mode = Node.PROCESS_MODE_ALWAYS

func _process(_delta: float) -> void:
	_frame += 1
	if _frame % 15 != 0:
		return
	for k in _held:
		_send_key(k, false)
	_held.clear()
	for i in _rng.randi_range(1, 2):
		var k: int = KEYS[_rng.randi() % KEYS.size()]
		_send_key(k, true)
		_held.append(k)
	var look := InputEventMouseMotion.new()
	look.relative = Vector2(_rng.randf_range(-40, 40), _rng.randf_range(-20, 20))
	Input.parse_input_event(look)
	if _rng.randf() < 0.2:
		var vp := get_viewport().get_visible_rect().size
		var pos := Vector2(_rng.randf() * vp.x, _rng.randf() * vp.y)
		for pressed in [true, false]:
			var e := InputEventMouseButton.new()
			e.button_index = MOUSE_BUTTON_LEFT
			e.pressed = pressed
			e.position = pos
			e.global_position = pos
			Input.parse_input_event(e)

func _send_key(k: int, pressed: bool) -> void:
	var e := InputEventKey.new()
	e.keycode = k
	e.physical_keycode = k
	e.pressed = pressed
	Input.parse_input_event(e)
