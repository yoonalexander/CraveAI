from backend.services.menu_evidence import ParsedPage, _parse_html
from backend.services.menu_index import select_menu_index_dishes
from backend.services.menu_markup import MenuPrice


def test_menu_index_covers_other_families_after_a_long_pho_section():
    pho = ParsedPage(
        menu_items=[(f"P{index}. Phở topping {index}", "") for index in range(1, 23)],
        menu_prices={"p22. phở topping 22": (MenuPrice(1595, "CAD"),)},
    )
    other_dishes = [
        "Gỏi Cuốn", "Chicken Fried Rice", "Bánh Mì", "Cơm Tấm",
        "Bún Thịt Nướng", "Green Papaya Salad", "Grilled Chicken Wings", "Mango Sticky Rice",
    ]
    other = ParsedPage(menu_items=[(name, "") for name in other_dishes])

    selected = select_menu_index_dishes([("https://example.com/pho", pho), ("https://example.com/menu", other)])

    assert len(selected) == 10
    assert [dish.name for dish in selected[1:9]] == other_dishes
    assert selected[0].name == "P22. Phở topping 22"
    assert selected[0].prices == (MenuPrice(1595, "CAD"),)
    assert selected[9].family == selected[0].family == "pho"


def test_menu_index_caps_a_single_family_and_uses_one_source_for_duplicates():
    first = ParsedPage(menu_items=[("P1. Beef Phở", "Served with herbs")])
    second = ParsedPage(
        menu_items=[("Beef Pho", ""), ("Chicken Pho", ""), ("Tofu Pho", "")],
        menu_prices={"beef pho": (MenuPrice(1500, "CAD"),)},
    )

    selected = select_menu_index_dishes([("https://example.com/first", first), ("https://example.com/second", second)])

    assert [dish.name for dish in selected] == ["Beef Pho", "Chicken Pho"]
    assert selected[0].source_url == "https://example.com/second"
    assert selected[0].description == ""
    assert selected[0].prices == (MenuPrice(1500, "CAD"),)


def test_menu_index_caps_a_menu_with_more_than_ten_distinct_families():
    page = ParsedPage(menu_items=[
        *((f"Special number {index}", "") for index in range(15)),
        ("Beef Pho", ""), ("Chicken Pho", ""),
    ])

    selected = select_menu_index_dishes([("https://example.com/menu", page)])

    assert len(selected) == len({dish.family for dish in selected}) == 10
    assert selected[0].family == "pho"
    assert selected[-1].name == "Special number 14"


def test_menu_index_keeps_quantities_and_groups_combos_by_the_main_dish():
    page = ParsedPage(menu_items=[
        ("2 Eggs", ""), ("3 Eggs", ""),
        ("Beef Pho with Spring Rolls", ""), ("Fresh Spring Rolls", ""),
        ("Vermicelli Bowl with Spring Rolls", ""),
    ])

    selected = select_menu_index_dishes([("https://example.com/menu", page)])

    assert {dish.name: dish.family for dish in selected} == {
        "2 Eggs": "2 eggs",
        "3 Eggs": "3 eggs",
        "Beef Pho with Spring Rolls": "pho",
        "Fresh Spring Rolls": "spring rolls",
        "Vermicelli Bowl with Spring Rolls": "vermicelli bowls",
    }


def test_menu_index_skips_explicit_beverage_categories():
    page = _parse_html("""
        <article class="wrapper-menu-item">
          <div class="menus_category-cocktails"><h4 class="menu-item__title-main">Orchard</h4></div>
        </article>
        <article class="wrapper-menu-item">
          <div class="menus_category-entrees"><h4 class="menu-item__title-main">Wine-Braised Beef</h4></div>
        </article>
    """)

    selected = select_menu_index_dishes([("https://example.com/menu", page)])

    assert page.menu_items == [("Orchard", ""), ("Wine-Braised Beef", "")]
    assert [dish.name for dish in selected] == ["Wine-Braised Beef"]
