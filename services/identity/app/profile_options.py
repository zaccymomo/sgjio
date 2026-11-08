"""The choices offered in profile setup (SCRUM-14).

Fixed lists rather than free text, so buddy matching (Module 2) can compare profiles by
exact value and recommendations can rely on a known set of interests. The front end
reads these from GET /api/profile/options, so this file is the only place to change them.
Stored values are these labels; renaming one means migrating existing profiles.
"""

INTERESTS = [
    "Food",
    "Cooking",
    "Hawker culture",
    "Festivals",
    "History",
    "Languages",
    "Music",
    "Film",
    "Art",
    "Photography",
    "Reading",
    "Football",
    "Badminton",
    "Running",
    "Hiking and nature",
    "Board games",
    "Gaming",
    "Technology",
    "Travel",
    "Volunteering",
]

LANGUAGES = [
    "English",
    "Mandarin",
    "Malay",
    "Tamil",
    "Cantonese",
    "Hokkien",
    "Teochew",
    "Hindi",
    "Bengali",
    "Urdu",
    "Telugu",
    "Tagalog",
    "Indonesian",
    "Vietnamese",
    "Thai",
    "Burmese",
    "Japanese",
    "Korean",
    "Arabic",
    "French",
    "German",
    "Spanish",
    "Portuguese",
    "Russian",
]

# Residential planning areas, plus the city centre as one choice. Precise enough to find
# a buddy nearby without asking for an address.
NEIGHBOURHOODS = [
    "Ang Mo Kio",
    "Bedok",
    "Bishan",
    "Bukit Batok",
    "Bukit Merah",
    "Bukit Panjang",
    "Bukit Timah",
    "Central (City and Orchard)",
    "Choa Chu Kang",
    "Clementi",
    "Geylang",
    "Hougang",
    "Jurong East",
    "Jurong West",
    "Kallang",
    "Marine Parade",
    "Novena",
    "Pasir Ris",
    "Punggol",
    "Queenstown",
    "Sembawang",
    "Sengkang",
    "Serangoon",
    "Tampines",
    "Tengah",
    "Toa Payoh",
    "Woodlands",
    "Yishun",
]
