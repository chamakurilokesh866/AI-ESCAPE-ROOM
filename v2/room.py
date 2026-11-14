"""Room configuration for Version 2 (the same Locked Library as V1).

Everything the game *engine* needs lives here as plain Python data. The
important difference from V1 is how it is used:

* PUBLIC text is only sent to the LLM after the player has actually
  discovered it (the engine decides when).
* SECRETS (the two codes) are never sent to the LLM at all. Python compares
  the player's input against them.
"""

TITLE = "The Locked Library"

INTRO = (
    "You wake up on a cold wooden floor. Dusty shelves tower around you and the "
    "smell of old paper fills the air. You are inside a small private library. "
    "The only exit is a heavy oak door with a four-digit keypad. A desk, a tall "
    "bookshelf, a large painting and a locked drawer are the only things in the "
    "room. Somehow, you have to get out."
)

# --- Secrets: checked by Python, never placed in any prompt -----------------
SECRETS = {
    "drawer": "5842",  # book digits in season order (spring, summer, autumn, winter)
    "door": "1847",    # MDCCCXLVII from the librarian's diary
}

# --- Fixed objects in the room (cannot be picked up) ------------------------
OBJECTS = ["desk", "bookshelf", "painting", "drawer", "door", "compartment"]

# Objects that exist but are hidden until the engine reveals them.
HIDDEN_OBJECTS = {"compartment"}

# --- Collectible items and where they start ---------------------------------
ITEMS = {
    "note": "desk",
    "magnifying glass": "desk",
    "brass key": "drawer",
    "index card": "drawer",
    "diary": "compartment",
}

# --- Puzzles (ids used in the game state) -----------------------------------
PUZZLES = {
    "season_books": "Season books: open the drawer with the code hidden in the books",
    "tiny_writing": "Tiny writing: read the index card with the magnifying glass",
    "hidden_compartment": "Hidden compartment: open it with the brass key and read the diary",
}
FINAL_CHALLENGE = "Escape: enter the door code on the keypad"

# --- Descriptions revealed to the player (and the narrator) -----------------
DESCRIPTIONS = {
    "room": (
        "A small private library: a mahogany desk with a built-in drawer, a tall "
        "bookshelf, a large painting of an old librarian, and a heavy oak door "
        "with a four-digit keypad."
    ),
    "desk": (
        "An old mahogany desk. A folded note and a brass magnifying glass lie on "
        "top. A drawer with a four-digit combination lock is built into it."
    ),
    "desk_empty": "An old mahogany desk with a built-in drawer. Nothing else lies on top.",
    "bookshelf": (
        "A tall bookshelf full of dusty books. Four books stick out slightly: "
        "'Winter's Tale', 'Spring Awakening', 'Summer Light' and 'Autumn Leaves'. "
        "Each has a single handwritten digit on its first page: Winter's Tale 2, "
        "Spring Awakening 5, Summer Light 8, Autumn Leaves 4."
    ),
    "painting": (
        "A large oil portrait of the old librarian. Behind the frame you find a "
        "small metal compartment set into the wall, with a keyhole."
    ),
    "drawer_locked": "The desk drawer is shut with a four-digit combination lock.",
    "drawer_open": "The drawer is open.",
    "door": (
        "A heavy oak door secured with a four-digit electronic keypad. It is the "
        "only way out."
    ),
    "compartment_locked": "A small metal compartment behind the painting. It has a keyhole.",
    "compartment_open": "The metal compartment behind the painting is open.",
    "note": "The note reads: 'Read the year as it turns: spring, summer, autumn, winter.'",
    "magnifying glass": "A brass magnifying glass. Useful for reading very small writing.",
    "brass key": "A small brass key.",
    "index card_blurry": (
        "A yellowed index card covered in tiny, faded writing. It is far too small "
        "to read with the naked eye."
    ),
    "index card": (
        "Through the magnifying glass the tiny writing on the index card reads: "
        "'The door remembers the year I was born.'"
    ),
    "diary": (
        "The librarian's diary. The first page says: 'Born in the year MDCCCXLVII.'"
    ),
}

# --- Words the player may use for each object/item (used for normalisation) --
ALIASES = {
    "desk": ["desk", "table"],
    "bookshelf": ["bookshelf", "bookshelves", "shelf", "shelves", "books", "book", "bookcase"],
    "painting": ["painting", "portrait", "picture", "frame"],
    "drawer": ["drawer", "combination lock", "lock"],
    "door": ["door", "keypad", "exit", "oak door"],
    "compartment": ["compartment", "keyhole", "safe", "wall safe"],
    "note": ["note", "paper", "folded note"],
    "magnifying glass": ["magnifying glass", "magnifier", "glass", "lens"],
    "brass key": ["brass key", "key", "small key"],
    "index card": ["index card", "card"],
    "diary": ["diary", "journal", "librarian's diary"],
}

ALL_NAMES = OBJECTS + list(ITEMS)
