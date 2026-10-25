extends Node

# Game Constants
const BALL_RADIUS = 0.5
const BALL_SPEED = 12.0
const BALL_ACCEL = 10.0
const COIN_COUNT = 10
const TIME_LIMIT = 60.0
const PLATFORM_SIZE = 20.0

# State
var score = 0
var time_left = TIME_LIMIT
var game_over = false

# Nodes
var player: CharacterBody3D
var camera: Camera3D
var camera_pivot: Node3D
var ui_layer: CanvasLayer
var score_label: Label
var timer_label: Label
var msg_label: Label
var coins_nodes = []

func _ready():
	setup_environment()
	setup_platform()
	setup_player()
	setup_coins()
	setup_ui()

func setup_environment():
	var env = WorldEnvironment.new()
	var environment = Environment.new()
	environment.background_mode = Environment.BG_SKY
	var sky = ProceduralSkyMaterial.new()
	environment.sky = Sky.new()
	environment.sky.sky_material = sky
	env.environment = environment
	add_child(env)

	var light = DirectionalLight3D.new()
	light.position = Vector3(5, 10, 5)
	light.rotation_degrees = Vector3(-45, 45, 0)
	light.shadow_enabled = true
	add_child(light)

func setup_platform():
	var platform = StaticBody3D.new()
	var mesh_instance = MeshInstance3D.new()
	var box_mesh = BoxMesh.new()
	box_mesh.size = Vector3(PLATFORM_SIZE, 1, PLATFORM_SIZE)
	mesh_instance.mesh = box_mesh
	
	var material = StandardMaterial3D.new()
	material.albedo_color = Color(0.2, 0.5, 0.2)
	mesh_instance.material_override = material
	
	var collision = CollisionShape3D.new()
	var box_shape = BoxShape3D.new()
	box_shape.size = Vector3(PLATFORM_SIZE, 1, PLATFORM_SIZE)
	collision.shape = box_shape
	
	platform.add_child(mesh_instance)
	platform.add_child(collision)
	add_child(platform)

func setup_player():
	camera_pivot = Node3D.new()
	add_child(camera_pivot)
	
	camera = Camera3D.new()
	camera.position = Vector3(0, 6, 12)
	camera.current = true
	camera_pivot.add_child(camera)
	
	player = CharacterBody3D.new()
	player.position = Vector3(0, 2, 0)
	
	var mesh_instance = MeshInstance3D.new()
	var sphere_mesh = SphereMesh.new()
	sphere_mesh.radius = BALL_RADIUS
	sphere_mesh.height = BALL_RADIUS * 2
	mesh_instance.mesh = sphere_mesh
	
	var material = StandardMaterial3D.new()
	material.albedo_color = Color(0.8, 0.2, 0.2)
	mesh_instance.material_override = material
	
	var collision = CollisionShape3D.new()
	var sphere_shape = SphereShape3D.new()
	sphere_shape.radius = BALL_RADIUS
	collision.shape = sphere_shape
	
	player.add_child(mesh_instance)
	player.add_child(collision)
	add_child(player)

func setup_coins():
	for i in range(COIN_COUNT):
		var coin = Area3D.new()
		var rx = randf_range(-PLATFORM_SIZE/2 + 1, PLATFORM_SIZE/2 - 1)
		var rz = randf_range(-PLATFORM_SIZE/2 + 1, PLATFORM_SIZE/2 - 1)
		coin.position = Vector3(rx, 1.2, rz)
		
		var mesh_instance = MeshInstance3D.new()
		var cylinder_mesh = CylinderMesh.new()
		cylinder_mesh.top_radius = 0.3
		cylinder_mesh.bottom_radius = 0.3
		cylinder_mesh.height = 0.1
		mesh_instance.mesh = cylinder_mesh
		mesh_instance.rotation_degrees = Vector3(90, 0, 0)
		
		var material = StandardMaterial3D.new()
		material.albedo_color = Color(1, 0.84, 0)
		material.metallic = 1.0
		mesh_instance.material_override = material
		
		var collision = CollisionShape3D.new()
		var cylinder_shape = CylinderShape3D.new()
		# CylinderShape3D only has 'radius' and 'height' in Godot 4
		cylinder_shape.radius = 0.3
		cylinder_shape.height = 0.1
		collision.shape = cylinder_shape
		collision.rotation_degrees = Vector3(90, 0, 0)
		
		coin.add_child(mesh_instance)
		coin.add_child(collision)
		
		coin.set_meta("mesh", mesh_instance)
		coin.body_entered.connect(func(body): _on_coin_collected(body, coin))
		
		add_child(coin)
		coins_nodes.append(coin)

func setup_ui():
	ui_layer = CanvasLayer.new()
	add_child(ui_layer)
	
	score_label = Label.new()
	score_label.position = Vector2(20, 20)
	score_label.text = "Coins: 0 / 10"
	ui_layer.add_child(score_label)
	
	timer_label = Label.new()
	timer_label.position = Vector2(20, 50)
	timer_label.text = "Time: 60s"
	ui_layer.add_child(timer_label)
	
	msg_label = Label.new()
	msg_label.position = Vector2(0, 0)
	msg_label.size = Vector2(1152, 648)
	msg_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	msg_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	msg_label.text = ""
	ui_layer.add_child(msg_label)

func _process(delta):
	if game_over:
		if Input.is_key_pressed(KEY_R):
			get_tree().reload_current_scene()
		return

	time_left -= delta
	if time_left <= 0:
		time_left = 0
		end_game(false)
	
	timer_label.text = "Time: %ds" % int(ceil(time_left))
	
	var input_dir = Vector3.ZERO
	if Input.is_key_pressed(KEY_W): input_dir.z -= 1
	if Input.is_key_pressed(KEY_S): input_dir.z += 1
	if Input.is_key_pressed(KEY_A): input_dir.x -= 1
	if Input.is_key_pressed(KEY_D): input_dir.x += 1
	
	input_dir = input_dir.normalized()
	
	var target_vel = input_dir * BALL_SPEED
	player.velocity.x = lerp(player.velocity.x, target_vel.x, BALL_ACCEL * delta)
	player.velocity.z = lerp(player.velocity.z, target_vel.z, BALL_ACCEL * delta)
	
	if not player.is_on_floor():
		player.velocity.y -= 20.0 * delta
	
	player.move_and_slide()
	
	camera_pivot.position = player.position
	camera.look_at(player.position)
	
	if player.position.y < -5:
		player.position = Vector3(0, 2, 0)
		player.velocity = Vector3.ZERO

	for coin in coins_nodes:
		if is_instance_valid(coin):
			var mesh = coin.get_meta("mesh")
			mesh.rotate_y(delta * 3.0)

func _on_coin_collected(body, coin):
	if body == player and not game_over:
		score += 1
		score_label.text = "Coins: %d / %d" % [score, COIN_COUNT]
		coin.queue_free()
		if score >= COIN_COUNT:
			end_game(true)

func end_game(success):
	game_over = true
	if success:
		msg_label.text = "YOU WIN!\nPress R to restart"
		msg_label.modulate = Color(0, 1, 0)
	else:
		msg_label.text = "TIME'S UP!\nPress R to restart"
		msg_label.modulate = Color(1, 0, 0)
