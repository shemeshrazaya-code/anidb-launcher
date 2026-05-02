from __future__ import annotations

from .models import AnimeDetail

DEMO_ANIME: list[AnimeDetail] = [
    AnimeDetail(
        aid=1,
        title="Crest of the Stars",
        description=(
            "Jinto Linn was a boy when his planet, Martine, was conquered by the "
            "Abh Empire. As the son of the planet's president, Jinto inherits "
            "noble status and is sent to study among the Abh."
        ),
        rating=7.52,
        rating_count=3651,
        picture_url="https://cdn.anidb.net/images/main/11788.jpg",
        type="TV Series",
        episode_count=13,
    ),
    AnimeDetail(
        aid=22,
        title="Cowboy Bebop",
        description=(
            "In the year 2071, humanity has colonised the entire Solar System. "
            "A ragtag group of bounty hunters chase deadbeats across the stars "
            "aboard the spaceship Bebop."
        ),
        rating=8.85,
        rating_count=12345,
        picture_url="https://cdn.anidb.net/images/main/59065.jpg",
        type="TV Series",
        episode_count=26,
    ),
    AnimeDetail(
        aid=979,
        title="Mushi-Shi",
        description=(
            "Ginko travels the countryside investigating mushi: primitive "
            "life-forms that exist alongside but apart from the world we know. "
            "His work brings him into contact with the wonders and tragedies "
            "they cause."
        ),
        rating=9.10,
        rating_count=8200,
        picture_url="https://cdn.anidb.net/images/main/6657.jpg",
        type="TV Series",
        episode_count=26,
    ),
    AnimeDetail(
        aid=2369,
        title="Ergo Proxy",
        description=(
            "In the dome city of Romdo, the citizens are served by AutoReivs, "
            "humanoid robots. When a virus begins giving these machines self-"
            "awareness, inspector Re-l Mayer investigates a series of related "
            "killings and uncovers a deeper conspiracy."
        ),
        rating=7.95,
        rating_count=4100,
        picture_url="https://cdn.anidb.net/images/main/29196.jpg",
        type="TV Series",
        episode_count=23,
    ),
    AnimeDetail(
        aid=4097,
        title="Mononoke",
        description=(
            "A wandering medicine seller hunts mononoke — supernatural spirits "
            "born of human regret and rage. To exorcise them he must uncover "
            "their Form, Truth, and Reason."
        ),
        rating=8.40,
        rating_count=5300,
        picture_url="https://cdn.anidb.net/images/main/40523.jpg",
        type="TV Series",
        episode_count=12,
    ),
]
