extends Node2D

# Game Constants
const PADDLE_WIDTH = 120
const PADDLE_HEIGHT = 20
const BALL_RADIUS = 8
const BALL_SPEED = 300.0
const BRICK_ROWS = 5
const BRICK_COLS = 8
const BRICK_HEIGHT = 30
const BRICK_MARGIN = 4

var score = 0
var lives = 3
var game_over = false
var game_won = false

# Nodes
var paddle: ColorRect
var ball: ColorRect
var score_label: Label
var lives_label: Label
var msg_label: Label
var bricks_container: Node2D

# State
var ball_velocity = Vector2(BALL_SPEED, -BALL_SPEED)
var paddle_current_width = PADDLE_WIDTH

func _ready():
	setup_ui()
	setup_game()

func setup_ui():
	score_label = Label.new()
	score_label.position = Vector2(20, 20)
	score_label.text = "Score: 0"
	add_child(score_label)
	
	lives_label = Label.new()
	lives_label.position = Vector2(20, 45)
	lives_label.text = "Lives: 3"
	add_child(lives_label)
	
	msg_label = Label.new()
	msg_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	msg_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	msg_label.text = ""
	add_child(msg_label)

func setup_game():
	# Paddle
	paddle = ColorRect.new()
	paddle.size = Vector2(PADDLE_WIDTH, PADDLE_HEIGHT)
	paddle.color = Color.WHITE
	paddle.position = Vector2(576 - PADDLE_WIDTH/2, 600)
	add_child(paddle)
	
	# Ball
	ball = ColorRect.new()
	ball.size = Vector2(BALL_RADIUS * 2, BALL_RADIUS * 2)
	ball.color = Color.YELLOW
	ball.position = Vector2(576, 580)
	add_child(ball)
	
	# Bricks
	bricks_container = Node2D.new()
	add_child(bricks_container)
	
	var brick_width = (1152 - (BRICK_MARGIN * (BRICK_COLS + 1))) / BRICK_COLS
	var colors = [Color.RED, Color.ORANGE, Color.YELLOW, Color.GREEN, Color.BLUE]
	
	for r in range(BRICK_ROWS):
		for c in range(BRICK_COLS):
			var brick = ColorRect.new()
			brick.size = Vector2(brick_width - BRICK_MARGIN, BRICK_HEIGHT - BRICK_MARGIN)
			brick.position = Vector2(
				BRICK_MARGIN + c * brick_width,
				100 + r * BRICK_HEIGHT
			)
			brick.color = colors[r]
			brick.name = "brick"
			bricks_container.add_child(brick)

func _process(delta):
	if game_over or game_won:
		if Input.is_key_pressed(KEY_R):
			restart_game()
		return

	# Paddle movement
	if Input.is_key_pressed(KEY_LEFT):
		paddle.position.x -= 500 * delta
	if Input.is_key_pressed(KEY_RIGHT):
		paddle.position.x += 500 * delta
	
	# Keep paddle on screen
	paddle.position.x = clamp(paddle.position.x, 0, 1152 - paddle.size.x)
	
	# Ball movement
	ball.position += ball_velocity * delta
	
	# Wall collisions
	if ball.position.x <= 0 or ball.position.x >= 1152 - ball.size.x:
		ball_velocity.x *= -1
	if ball.position.y <= 0:
		ball_velocity.y *= -1
	
	# Paddle collision
	var ball_rect = Rect2(ball.position, ball.size)
	var paddle_rect = Rect2(paddle.position, paddle.size)
	if ball_rect.intersects(paddle_rect):
		if ball_velocity.y > 0:
			ball_velocity.y *= -1
			# Angle based on where it hits the paddle
			var hit_pos = (ball.position.x + BALL_RADIUS) - (paddle.position.x + paddle.size.x/2)
			ball_velocity.x = hit_pos * 2.0

	# Brick collisions
	for brick in bricks_container.get_children():
		var brick_rect = Rect2(brick.position, brick.size)
		if ball_rect.intersects(brick_rect):
			ball_velocity.y *= -1
			bricks_container.remove_child(brick)
			brick.queue_free()
			score += 10
			score_label.text = "Score: %d" % score
			
			# Power-up: Chance to widen paddle
			if randf() < 0.15:
				apply_powerup()
			break

	# Lose life
	if ball.position.y > 648:
		lives -= 1
		lives_label.text = "Lives: %d" % lives
		if lives <= 0:
			end_game(false)
		else:
			reset_ball()

	# Win condition
	if bricks_container.get_child_count() == 0:
		end_game(true)

func apply_powerup():
	paddle_current_width = PADDLE_WIDTH * 1.5
	paddle.size.x = paddle_current_width
	# Reset width after 5 seconds
	await get_tree().create_timer(5.0).timeout
	paddle.size.x = PADDLE_WIDTH
	paddle_current_width = PADDLE_WIDTH

func reset_ball():
	ball.position = Vector2(576, 580)
	ball_velocity = Vector2(BALL_SPEED, -BALL_SPEED)

func end_game(won):
	if won:
		game_won = true
		msg_label.text = "YOU WIN!\nPress R to Restart"
	else:
		game_over = true
		msg_label.text = "GAME OVER\nPress R to Restart"

func restart_game():
	get_tree().reload_current_scene()
