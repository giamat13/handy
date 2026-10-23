"""שמות בעברית למחוות ולפעולות, וברירות המחדל של המיפוי."""

GESTURES = {
    "wink_left": "קריצה שמאל",
    "wink_right": "קריצה ימין",
    "pinch": "צביטה",
    "ok": "אוקיי",
    "peace": "ניצחון (V)",
    "thumbs_up": "לייק",
    "thumbs_down": "דיסלייק",
    "fist": "אגרוף",
    "open": "כף פתוחה",
    "point": "הצבעה",
    "three": "שלוש אצבעות",
    "rock": "רוק",
}

ACTIONS = {
    "none": "ללא",
    "left_click": "קליק שמאלי",
    "right_click": "קליק ימני",
    "double_click": "קליק כפול",
    "middle_click": "קליק אמצעי",
    "drag": "גרירה (בזמן המחווה)",
    "scroll_up": "גלילה למעלה",
    "scroll_down": "גלילה למטה",
}

DEFAULT_BINDINGS = {
    "wink_left": "left_click",
    "wink_right": "right_click",
    "pinch": "none",
    "ok": "double_click",
    "peace": "none",
    "thumbs_up": "scroll_up",
    "thumbs_down": "scroll_down",
    "fist": "none",
    "open": "none",
    "point": "none",
    "three": "none",
    "rock": "none",
}
