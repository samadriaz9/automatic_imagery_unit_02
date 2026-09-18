"""Shared hardware / imaging constants for main and GUI."""

IMAGING_ROWS = 7
IMAGING_COLS = 7
CAMERA_STEPSIZE = 112
PETRI_STEPSIZE = 116

PETRI_DISH_PRE_UP = 690
CAMERA_DISH_PRE_UP = 3850
PETRI_DISH_PRE_UP_ROW2 = 1460
CAMERA_DISH_PRE_UP_ROW2 = 3750

# Between dishes in a tray row: undo the within-dish petri travel so the next
# dish starts at the same PRE_UP height (do not use a fixed *7 from the old 8-row grid).
PETRI_OFFSET_PER_DISH = PETRI_STEPSIZE * (IMAGING_ROWS - 1)
CAMERA_OFFSET_PER_DISH = CAMERA_STEPSIZE
# After the between-dish camera DOWN, move back away from the limit (dishes 2–5).
CAMERA_BETWEEN_DISH_AWAY_STEPS = 20

# Mosaic: dish covers ~6.5 of 7 columns and ~6.25 of 7 rows — trim the overflow
# from the last capture column / last capture row after stitching.
MOSAIC_TRIM_HALF_LAST_COLUMN = True
MOSAIC_LAST_ROW_COVER_FRACTION = 0.25  # keep 0.25 of last row (6 + 0.25 = 6.25)

PETRI_TRAY_ROWS = 2
PETRI_TRAY_COLS = 5
MAX_PETRI_DISHES = PETRI_TRAY_ROWS * PETRI_TRAY_COLS

# Steps panel — quick incubation (Start Incubation button)
STEP_INCUBATION_TEMP_C = 37.0
STEP_INCUBATION_MINUTES = 2.0

# Incubation + imaging study — up to 10 rounds (temp + time each)
NUM_STUDY_ROUNDS = 10
INCUBATION_TEMP_MIN = 20.0
INCUBATION_TEMP_MAX = 55.0
INCUBATION_TEMP_STEP = 1.0
DEFAULT_ROUND_TEMPS = (37.0,) * NUM_STUDY_ROUNDS
DEFAULT_ROUND_TIMES_MIN = (4.0,) * NUM_STUDY_ROUNDS
DEFAULT_ROUND_ENABLED = (True,) + (False,) * (NUM_STUDY_ROUNDS - 1)
INCUBATION_MIN_STEP = 0.5
INCUBATION_MIN_MIN = 0.5
INCUBATION_MIN_MAX = 600.0
INCUBATION_HOUR_STEP = 0.25

# Split imaging (10 dishes): row-1 capture → home → mid incubation → row-2 capture
MID_ROW_IMAGING_TEMP_C = 37.0
MID_ROW_IMAGING_MIN = 4.0
DISHES_PER_TRAY_ROW = PETRI_TRAY_COLS

# USB capture: short settle + flush stale frames before save
CAPTURE_SETTLE_SECONDS = 0.2
CAPTURE_FRAME_COUNT = 2
CAPTURE_DISCARD_FRAMES = 1  # of the 2 frames; save the last one
MOTION_SETTLE_SECONDS = 0.08  # short pause after motors (vibration)

# Camera disconnect during imaging: all home → incubate → retry the failed dish
CAMERA_DISCONNECT_RECOVERY_TEMP_C = 37.0
CAMERA_DISCONNECT_RECOVERY_MIN = 5.0
CAMERA_DISCONNECT_MAX_RECOVERIES = 5

# Legacy aliases (workflow / imports)
NUM_INCUBATION_SLOTS = 3
NUM_PICTURE_SLOTS = NUM_STUDY_ROUNDS
