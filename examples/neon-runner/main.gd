extends Node3D

# --- Game Constants ---
const LANES = [-4.0, 0.0, 4.0]
const INITIAL_SPEED = 25.0
const SPEED_INC = 0.15
const JUMP_FORCE = 12.0
const GRAVITY = -25.0
const SPAWN_DISTANCE = 80.0 

# --- State ---
var current_lane = 1 
var speed = INITIAL_SPEED
var score = 0.0
var distance = 0.0
var is_game_over = false
var is_jumping = false
var jump_velocity = 0.0

# --- Nodes ---
var player: MeshInstance3D
var camera: Camera3D
var hud: CanvasLayer
var score_label: Label
var speed_label: Label
var dist_label: Label
var game_over_panel: Control

var obstacles = []
var orbs = []
var buildings = []
var road_segments = []

func _ready():
	setup_environment()
	setup_player()
	setup_hud()
	setup_initial_world()

func setup_environment():
	var env = WorldEnvironment.new()
	var environment = Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.02, 0.02, 0.05)
	
	environment.fog_enabled = true
	environment.fog_light_color = Color(0.02, 0.02, 0.05)
	environment.fog_density = 0.05
	# Removed FOG_EXPONENTIAL as it's not available in the current context
	
	environment.glow_enabled = true
	environment.glow_bloom = 0.2
	environment.glow_intensity = 1.0
	
	env.environment = environment
	add_child(env)

	var light = DirectionalLight3D.new()
	light.position = Vector3(0, 10, 0)
	light.rotation_degrees = Vector3(-45, 45, 0)
	light.light_energy = 0.5
	add_child(light)

func setup_player():
	player = MeshInstance3D.new()
	var mesh = BoxMesh.new()
	mesh.size = Vector3(0.8, 0.4, 2.0)
	player.mesh = mesh
	
	var mat = StandardMaterial3D.new()
	mat.albedo_color = Color(0, 1, 1) 
	mat.emission_enabled = true
	mat.emission = Color(0, 1, 1)
	mat.emission_energy_multiplier = 5.0
	player.material_override = mat
	
	add_child(player)
	player.position = Vector3(LANES[current_lane], 0.5, 0)

	camera = Camera3D.new()
	camera.position = Vector3(0, 3.0, -6.0)
	camera.rotation_degrees = Vector3(-10, 0, 0)
	add_child(camera)

func setup_hud():
	hud = CanvasLayer.new()
	add_child(hud)

	var container = Control.new()
	container.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	hud.add_child(container)

	score_label = Label.new()
	score_label.position = Vector2(30, 30)
	score_label.add_theme_color_override("font_color", Color(1, 0, 1))
	container.add_child(score_label)

	speed_label = Label.new()
	speed_label.position = Vector2(30, 60)
	speed_label.add_theme_color_override("font_color", Color(0, 1, 1))
	container.add_child(speed_label)

	dist_label = Label.new()
	dist_label.position = Vector2(30, 90)
	dist_label.add_theme_color_override("font_color", Color(0.8, 0.8, 1))
	container.add_child(dist_label)

	game_over_panel = Control.new()
	game_over_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	game_over_panel.visible = false
	hud.add_child(game_over_panel)

	var go_label = Label.new()
	go_label.text = "GAME OVER\nPress R to Restart"
	go_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	go_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	go_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	go_label.add_theme_color_override("font_color", Color(1, 0, 0))
	game_over_panel.add_child(go_label)

func setup_initial_world():
	for i in range(40):
		create_road_segment(i * 20)
		create_building_pair(i * 20)

func create_road_segment(z):
	var road = MeshInstance3D.new()
	var mesh = PlaneMesh.new()
	mesh.size = Vector2(15, 20)
	road.mesh = mesh
	
	var mat = StandardMaterial3D.new()
	mat.albedo_color = Color(0.05, 0.05, 0.07)
	road.material_override = mat
	
	road.position = Vector3(0, 0, z)
	add_child(road)
	road_segments.append(road)

	for x in [-2.0, 2.0]:
		var line = MeshInstance3D.new()
		var lmesh = BoxMesh.new()
		lmesh.size = Vector3(0.15, 0.02, 20)
		line.mesh = lmesh
		var lmat = StandardMaterial3D.new()
		lmat.albedo_color = Color(1, 0, 1) if x < 0 else Color(0, 1, 1)
		lmat.emission_enabled = true
		lmat.emission = lmat.albedo_color
		lmat.emission_energy_multiplier = 5.0
		line.material_override = lmat
		line.position = Vector3(x, 0.01, z)
		add_child(line)
		road_segments.append(line)

func create_building_pair(z):
	var colors = [Color(1, 0, 1), Color(0, 1, 1), Color(0.5, 0, 1)]
	for side in [-1, 1]:
		var b = MeshInstance3D.new()
		var mesh = BoxMesh.new()
		mesh.size = Vector3(6, randf_range(15, 60), 6)
		b.mesh = mesh
		
		var mat = StandardMaterial3D.new()
		mat.albedo_color = Color(0.02, 0.02, 0.05)
		b.material_override = mat
		
		b.position = Vector3(side * 13, mesh.size.y / 2, z)
		add_child(b)
		buildings.append(b)
		
		var strip = MeshInstance3D.new()
		var smesh = BoxMesh.new()
		smesh.size = Vector3(0.3, mesh.size.y, 6.3)
		strip.mesh = smesh
		var smat = StandardMaterial3D.new()
		smat.albedo_color = colors[randi() % colors.size()]
		smat.emission_enabled = true
		smat.emission = smat.albedo_color
		smat.emission_energy_multiplier = 8.0
		strip.material_override = smat
		strip.position = Vector3(side * -3.1, 0, 0)
		b.add_child(strip)

func spawn_obstacle():
	var z = player.position.z + SPAWN_DISTANCE
	var lane = randi() % 3
	
	if randf() > 0.3:
		var obs = MeshInstance3D.new()
		var mesh = BoxMesh.new()
		mesh.size = Vector3(3, 2, 1)
		obs.mesh = mesh
		var mat = StandardMaterial3D.new()
		mat.albedo_color = Color(1, 0, 0)
		mat.emission_enabled = true
		mat.emission = Color(1, 0, 0)
		mat.emission_energy_multiplier = 10.0
		obs.material_override = mat
		obs.position = Vector3(LANES[lane], 1, z)
		add_child(obs)
		obstacles.append(obs)
	else:
		var orb = MeshInstance3D.new()
		var mesh = SphereMesh.new()
		mesh.radius = 0.6
		mesh.height = 1.2
		orb.mesh = mesh
		var mat = StandardMaterial3D.new()
		mat.albedo_color = Color(1, 1, 0)
		mat.emission_enabled = true
		mat.emission = Color(1, 1, 0)
		mat.emission_energy_multiplier = 10.0
		orb.material_override = mat
		orb.position = Vector3(LANES[lane], 1, z)
		add_child(orb)
		orbs.append(orb)

func _process(delta):
	if is_game_over:
		if Input.is_key_pressed(KEY_R):
			get_tree().reload_current_scene()
		return

	speed += SPEED_INC * delta
	distance += speed * delta
	score += speed * delta * 0.1

	player.position.z += speed * delta
	
	var target_x = LANES[current_lane]
	player.position.x = lerp(player.position.x, target_x, 15.0 * delta)
	
	if is_jumping:
		jump_velocity += GRAVITY * delta
		player.position.y += jump_velocity * delta
		if player.position.y <= 0.5:
			player.position.y = 0.5
			is_jumping = false
			jump_velocity = 0.0

	camera.position.z = player.position.z - 8.0
	camera.position.y = 3.0
	camera.look_at(Vector3(0, 1, player.position.z + 10))

	if randf() < 0.04:
		spawn_obstacle()

	cleanup_old_objects()
	check_collisions()

	score_label.text = "SCORE: %d" % int(score)
	speed_label.text = "SPEED: %d km/h" % int(speed * 5)
	dist_label.text = "DIST: %d m" % int(distance)

func _unhandled_input(event):
	if is_game_over: return

	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_A or event.keycode == KEY_LEFT:
			current_lane = clamp(current_lane - 1, 0, 2)
		elif event.keycode == KEY_D or event.keycode == KEY_RIGHT:
			current_lane = clamp(current_lane + 1, 0, 2)
		elif event.keycode == KEY_SPACE and not is_jumping:
			is_jumping = true
			jump_velocity = JUMP_FORCE

func check_collisions():
	for obs in obstacles:
		if abs(player.position.z - obs.position.z) < 1.5:
			if abs(player.position.x - obs.position.x) < 2.0:
				if player.position.y < 2.0:
					game_over()
					return
	
	for orb in orbs:
		if player.position.distance_to(orb.position) < 2.0:
			score += 100
			orbs.erase(orb)
			orb.queue_free()

func cleanup_old_objects():
	var threshold = player.position.z - 20
	
	for road in road_segments:
		if road.position.z < threshold:
			road.position.z += 800 

	for obs in obstacles:
		if obs.position.z < threshold:
			obstacles.erase(obs)
			obs.queue_free()
	for orb in orbs:
		if orb.position.z < threshold:
			orbs.erase(orb)
			orb.queue_free()
	for b in buildings:
		if b.position.z < threshold:
			buildings.erase(b)
			b.queue_free()
			create_building_pair(player.position.z + 800)

func game_over():
	is_game_over = true
	game_over_panel.visible = true
	player.material_override.albedo_color = Color(1, 0, 0)
	player.material_override.emission = Color(1, 0, 0)
