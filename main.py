import argparse
import datetime
import json
import logging
import pathlib
import time
from typing import Collection, Tuple

import networkx as nx

from wiki_categories import Assets, CategoryTree
from wiki_categories.assets import ProgressManager, LocalAssetSource
from wiki_categories.category_tree import less_than_page_count_percentile
from wiki_categories.wiki_utils import (
    CategoryNotFound,
    id_for_category_str_by_lang,
)


class TimedPercentageProgressManager(ProgressManager):
    """
    Logs current progress percentage every 60 seconds.
    """

    total: int
    last_time: float

    acc: int = 0
    duration: float = 30.0

    progress_time_format: str = "%H:%M:%S"

    def start(self, total: int) -> None:
        logging.info("Starting job")
        self.total = total
        self.last_time = time.time()

    def update(self, n: int) -> None:
        self.acc += n

        current_time = time.time()

        if (current_time - self.last_time) > self.duration:
            self.last_time = current_time
            percentage_str = f"{(self.acc / self.total) * 100:0.1f}%"

            logging.info(
                f"[ {percentage_str: >5} ]  "
                f"{datetime.datetime.now().strftime(self.progress_time_format)}"
            )

    def close(self) -> None:
        self.acc = 0
        logging.info("Finished job")


def _split_lines(text: str) -> Tuple[str, ...]:
    return tuple(x.strip() for x in text.splitlines() if x.strip())


_default_excluded_categories = _split_lines(
    """
    Category:Hidden categories
    Category:Tracking categories
    Category:Noindexed pages
    """
)


def get_root_category_id(lang: str) -> int:
    try:
        return id_for_category_str_by_lang(lang, "Category:Contents", "en")
    except CategoryNotFound:
        return id_for_category_str_by_lang(lang, "Category:Categories", "en")


def trim_tree(
    src_tree: CategoryTree,
    root_id: int,
    language: str,
    excluded_categories: Collection[str],
    depth_limit: int,
    page_percentile: int,
) -> None:
    total_excluded = set()

    for excluded in excluded_categories:
        try:
            excluded_id = id_for_category_str_by_lang(language, excluded, "en")
        except CategoryNotFound:
            continue
        total_excluded.update(
            x for x in src_tree.successors(excluded_id) if x != root_id
        )
        total_excluded.add(excluded_id)

    src_tree.remove_nodes_from(total_excluded)

    reachable = nx.dfs_tree(src_tree, source=root_id, depth_limit=depth_limit)
    src_tree.remove_nodes_from([x for x in src_tree if x not in reachable])

    to_remove = less_than_page_count_percentile(src_tree, page_percentile)

    for n in to_remove:
        if n == root_id:
            continue
        src_tree.remove_node_reconstruct(n)


def generate_category_tree(language: str) -> CategoryTree:
    return CategoryTree(
        Assets(language, progress_manager=TimedPercentageProgressManager())
    )


def generate_category_tree_from_local(language: str, root_dir: pathlib.Path) -> CategoryTree:
    return CategoryTree(Assets.from_root_dir(language, root_dir))


def save_edges(src_tree: CategoryTree, to_path: pathlib.Path):
    edges = []

    for x in src_tree.nodes:
        attr_dict = src_tree.nodes[x]

        edges.append(
            {
                "_id": x,
                "name": attr_dict["name"],
                "predecessors": [
                    n for n in src_tree.predecessors(x)
                ],
                "successors": [
                    n for n in src_tree.successors(x)
                ],
            }
        )

    with open(to_path, "w", encoding="utf-8") as edges_f:
        json.dump(edges, edges_f, ensure_ascii=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "language",
        type=str,
        help="Specifies which Wikipedia language to save (ie. en, de, fr, etc.)",
    )

    parser.add_argument(
        "--depth-limit",
        type=int,
        help='Depth limit from "Category:Contents" (or the language root) to keep categories from.',
        default=100,
    )

    parser.add_argument(
        "--page-percentile",
        type=int,
        help="Minimum percentile to keep categories, considering the category's number of pages.",
        default=75,
    )

    parser.add_argument(
        "--excluded-categories",
        type=str,
        nargs="*",
        help="Category names to exclude from category tree.",
    )

    parser.add_argument(
        "--edges",
        type=str,
        default="edges.json",
        help="Filename to save category tree edges to.",
    )

    logging.getLogger().setLevel(logging.INFO)

    parser_vars = vars(parser.parse_args())

    _language = parser_vars["language"]
    _depth_limit = parser_vars["depth_limit"]
    _page_percentile = parser_vars["page_percentile"]

    _excluded_categories = parser_vars["excluded_categories"]
    _excluded_categories = (
        _default_excluded_categories
        if not _excluded_categories
        else _excluded_categories
    )

    _edges = pathlib.Path(parser_vars["edges"])

    logging.info(f"Starting {_language}wiki at {datetime.datetime.now()}.")

    category_tree = generate_category_tree_from_local(
        _language,
        pathlib.Path("./assets"),
    )

    trim_tree(
        category_tree,
        get_root_category_id(_language),
        _language,
        _excluded_categories,
        _depth_limit,
        _page_percentile,
    )

    save_edges(category_tree, _edges)

    logging.info(f"Finished {_language}wiki at {datetime.datetime.now()}.")
