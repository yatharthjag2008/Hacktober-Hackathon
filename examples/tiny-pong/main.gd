extends Node

func _ready():
	# Main game setup
	var game_scene = PongGame.new()
	add_child(game_scene)

class PongGame extends Node2D:
	var screen_size = Vector2(1152, 648)
	var paddle_height = 100
	var paddle_width = 20
	var ball_size = 20
	var winning_score = 5
	
	var player_score = 0
	var ai_score = 0
	var rally_count = 0
	var game_over = false
	
	var player_paddle: ColorRect
	var ai_paddle: ColorRect
	var ball: ColorRect
	var ball_velocity = Vector2(400, 400)
	
	var score_label: Label
	var rally_label: Label
	var result_label: Label
	
	func _ready():
		# Background
		var bg = ColorRect.new()
		bg.color = Color.BLACK
		bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		add_child(bg)
		
		# Player Paddle
		player_paddle = ColorRect.new()
		player_paddle.size = Vector2(paddle_width, paddle_height)
		player_paddle.position = Vector2(50, screen_size.y / 2 - paddle_height / 2)
		player_paddle.color = Color.WHITE
		add_child(player_paddle)
		
		# AI Paddle
		ai_paddle = ColorRect.new()
		ai_paddle.size = Vector2(paddle_width, paddle_height)
		ai_paddle.position = Vector2(screen_size.x - 50 - paddle_width, screen_size.y / 2 - paddle_height / 2)
		ai_paddle.color = Color.WHITE
		add_child(ai_paddle)
		
		# Ball
		ball = ColorRect.new()
		ball.size = Vector2(ball_size, ball_size)
		ball.position = screen_size / 2 - Vector2(ball_size/2, ball_size/2)
		ball.color = Color.RED
		add_child(ball)
		
		# UI
		var canvas = CanvasLayer.new()
		add_child(canvas)
		
		score_label = Label.new()
		score_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		score_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		score_label.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
		score_label.add_theme_color_override("font_color", Color.WHITE)
		score_label.add_theme_font_size_override("font_size", 48)
		canvas.add_child(score_label)
		
		rally_label = Label.new()
		rally_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		rally_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		rally_label.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
		rally_label.position.y = 60
		rally_label.add_theme_color_override("font_color", Color.WHITE)
		rally_label.add_theme_font_size_override("font_size", 24)
		canvas.add_child(rally_label)
		
		result_label = Label.new()
		result_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		result_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		result_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
		result_label.add_theme_color_override("font_color", Color.WHITE)
		result_label.add_theme_font_size_override("font_size", 64)
		result_label.text = ""
		canvas.add_child(result_label)
		
		update_hud()
		reset_ball()

	func update_hud():
		score_label.text = "Player: %d  |  AI: %d" % [player_score, ai_score]
		rally_label.text = "Rally: %d" % rally_count

	func reset_ball():
		ball.position = screen_size / 2 - Vector2(ball_size/2, ball_size/2)
		rally_count = 0
		update_hud()
		# Randomize starting direction
		var dir = Vector2(1, 1) if randf() > 0.5 else Vector2(-1, 1)
		dir.y = dir.y if randf() > 0.5 else -dir.y
		ball_velocity = dir.normalized() * 400

	func _process(delta):
		if game_over:
			if Input.is_key_pressed(KEY_R):
				restart_game()
			return

		# Player Movement
		var move_dir = 0
		if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
			move_dir -= 1
		if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
			move_dir += 1
		
		player_paddle.position.y += move_dir * 600 * delta
		player_paddle.position.y = clamp(player_paddle.position.y, 0, screen_size.y - paddle_height)
		
		# AI Movement (Fallible)
		var ai_center = ai_paddle.position.y + paddle_height / 2
		var ball_center = ball.position.y + ball_size / 2
		var ai_speed = 350
		
		if ball_center < ai_center - 10:
			ai_paddle.position.y -= ai_speed * delta
		elif ball_center > ai_center + 10:
			ai_paddle.position.y += ai_speed * delta
		
		ai_paddle.position.y = clamp(ai_paddle.position.y, 0, screen_size.y - paddle_height)
		
		# Ball Movement
		ball.position += ball_velocity * delta
		
		# Wall Collisions (Top/Bottom)
		if ball.position.y <= 0 or ball.position.y >= screen_size.y - ball_size:
			ball_velocity.y *= -1
			ball.position.y = clamp(ball.position.y, 0, screen_size.y - ball_size)
			
		# Paddle Collisions
		var ball_rect = Rect2(ball.position, ball.size)
		var player_rect = Rect2(player_paddle.position, player_paddle.size)
		var ai_rect = Rect2(ai_paddle.position, ai_paddle.size)
		
		if ball_rect.intersects(player_rect):
			if ball_velocity.x < 0:
				ball_velocity.x *= -1.1 # Speed up slightly
				ball_velocity.y += randf_range(-100, 100)
				rally_count += 1
				update_hud()
		
		if ball_rect.intersects(ai_rect):
			if ball_velocity.x > 0:
				ball_velocity.x *= -1.1 # Speed up slightly
				ball_velocity.y += randf_range(-100, 100)
				rally_count += 1
				update_hud()
				
		# Scoring
		if ball.position.x < 0:
			ai_score += 1
			check_win_condition()
			if not game_over:
				reset_ball()
		elif ball.position.x > screen_size.x:
			player_score += 1
			check_win_condition()
			if not game_over:
				reset_ball()
		
		update_hud()

	func check_win_condition():
		if player_score >= winning_score:
			game_over = true
			result_label.text = "VICTORY!"
		elif ai_score >= winning_score:
			game_over = true
			result_label.text = "DEFEAT!"

	func restart_game():
		player_score = 0
		ai_score = 0
		rally_count = 0
		game_over = false
		result_label.text = ""
		update_hud()
		reset_ball()
