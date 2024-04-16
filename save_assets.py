import pathlib

from wiki_categories.assets import Assets


if __name__ == "__main__":
    assets = Assets("en")
    assets.save_all(pathlib.Path("assets"))
