"""Room design for Version 1 of the AI Escape Room.

In Version 1 this description is *only* used to build the Game Master's
system prompt. Python does not track or enforce any of it: the LLM is
trusted to remember what the player has done, keep the puzzles consistent
and decide when the player has escaped. (Version 2 moves this logic into
Python.)
"""

ROOM = {
    "title": "The Locked Library",
    "intro": (
        "You wake up on a cold wooden floor. Dusty shelves tower around you and "
        "the smell of old paper fills the air. You are inside a small private "
        "library. The only exit is a heavy oak door with a four-digit keypad. "
        "A desk, a tall bookshelf, a large painting and a locked drawer are the "
        "only things in the room. Somehow, you have to get out."
    ),
    # Five interactive objects
    "objects": {
        "desk": (
            "An old mahogany desk. On top lies a folded note and a brass "
            "magnifying glass. The note reads: 'Read the year as it turns: "
            "spring, summer, autumn, winter.'"
        ),
        "bookshelf": (
            "A tall bookshelf full of dusty books. Four books stick out "
            "slightly: 'Winter's Tale', 'Spring Awakening', 'Summer Light' and "
            "'Autumn Leaves'. Each one has a single handwritten digit on its "
            "first page: Winter's Tale = 2, Spring Awakening = 5, "
            "Summer Light = 8, Autumn Leaves = 4."
        ),
        "painting": (
            "A large oil portrait of the old librarian. If the player looks "
            "behind it they find a small metal compartment with a keyhole. It "
            "can only be opened with the small brass key."
        ),
        "drawer": (
            "A desk drawer locked with a four-digit combination lock. The "
            "correct combination is 5842 (the book digits in season order). "
            "Inside: a small brass key and a yellowed index card covered in "
            "tiny, faded writing."
        ),
        "door": (
            "A heavy oak door secured with a four-digit electronic keypad. The "
            "correct code is 1847. Any other code makes the keypad beep red."
        ),
    },
    # Items the player can collect
    "items": {
        "note": "Found on the desk. Hint about the order of the seasons.",
        "magnifying glass": "Found on the desk. Lets the player read tiny writing.",
        "brass key": "Found in the drawer. Opens the compartment behind the painting.",
        "index card": (
            "Found in the drawer. The writing is too small to read without the "
            "magnifying glass. Read with the magnifying glass it says: "
            "'The door remembers the year I was born.'"
        ),
        "librarian's diary": (
            "Found in the compartment behind the painting. The first page "
            "says: 'Born in the year MDCCCXLVII.' (Roman numerals for 1847.)"
        ),
    },
    # Puzzles, in the intended order
    "puzzles": [
        "Puzzle 1 - Season books: put the four book digits in the season order "
        "from the desk note (spring 5, summer 8, autumn 4, winter 2) to get "
        "the drawer code 5842.",
        "Puzzle 2 - Tiny writing: use the magnifying glass on the index card "
        "to read 'The door remembers the year I was born.'",
        "Puzzle 3 - Hidden compartment: use the brass key on the compartment "
        "behind the painting to find the librarian's diary, which gives the "
        "birth year in Roman numerals: MDCCCXLVII = 1847.",
    ],
    "final_challenge": (
        "Enter 1847 on the door keypad. The door opens and the player escapes."
    ),
}
