from backend.services.menu_evidence import _parse_html
from backend.services.menu_index import select_menu_index_dishes
from backend.services.menu_markup import MenuPrice
from backend.services.menu_pdf import parse_menu_pdf_text
from scripts.probe_menu_index import menu_links


def test_menu_probe_extracts_scoped_cards_with_prices_and_leaves_unpriced_dishes_usable():
    page = _parse_html("""
        <article class="group">
          <img src="/assets/img/food/soup.webp" alt="Pork Bone Soup">
          <p class="leading-snug">Pork and potato broth</p>
        </article>
        <div class="food-item-holder">
          <div class="food-item-title"><h3>Caprese Salad</h3></div>
          <div class="food-price">$11.99/Regular</div>
          <div class="food-price">$19.99/Large</div>
        </div>
        <ul>
          <li><strong>Fried Calamari</strong> served with cocktail sauce 17.95 (410 Cals)</li>
          <li><strong>Family Special</strong> serves 2 (800 Cals)</li>
        </ul>
        <div class="menu-item">
          <div class="menu-item-title">Rendang</div>
          <div class="menu-item-description">Coconut and galangal</div>
        </div>
        <p class="p1"><b>Tuna Tartare | 25</b><em>With citrus</em></p>
        <section class="category" id="alcoholic">
          <div class="item" data-search="mimosa">
            <span class="item-name">Mimosa</span><span class="item-price">$13.00</span>
          </div>
        </section>
    """, menu_context=True)

    selected = select_menu_index_dishes([("https://example.com/menu", page)])

    assert [item.name for item in selected] == [
        "Pork Bone Soup", "Caprese Salad", "Fried Calamari", "Rendang", "Tuna Tartare",
    ]
    assert selected[0].prices == ()
    assert selected[1].prices == (MenuPrice(1199, option="Regular"), MenuPrice(1999, option="Large"))
    assert selected[2].prices == (MenuPrice(1795),)
    assert selected[2].description == "served with cocktail sauce"
    assert selected[4].prices == (MenuPrice(2500),)


def test_pdf_rows_keep_side_by_side_prices_separate_and_drop_conflicts():
    page = parse_menu_pdf_text("""
        House Menu
        BRUSCHETTA / 14.95                     BEEF CARPACCIO / 15.95
        Diced tomatoes and garlic             In-house cured beef
        BRUSCHETTA / 17.95
        Add chicken / 5.00
        Broccoli & cheddar 8.95 (360 Cals)
    """)

    assert page.menu_items == [("BRUSCHETTA", ""), ("BEEF CARPACCIO", "")]
    assert page.menu_prices == {"beef carpaccio": (MenuPrice(1595),)}


def test_probe_follows_food_documents_but_skips_self_links_drinks_and_unvetted_hosts():
    url = "https://example.com/menu"
    links = [
        ("#menu", "Menu"), ("/drinks", "Drinks"), ("/menu-1", "Cocktails"),
        ("https://other.example/menu.pdf", "Food Menu"),
        ("https://static1.squarespace.com/static/menu.pdf", "Lunch Menu"),
        ("/dine-in.pdf", "Lunch and Dinner"), ("/order", "Order Online"),
    ]

    assert menu_links(url, links, "example.com") == [
        "https://static1.squarespace.com/static/menu.pdf", "https://example.com/dine-in.pdf",
        "https://example.com/order",
    ]


def test_published_order_preview_prices_are_not_assigned_to_a_specific_location():
    page = _parse_html("""
        <div class="sub-item">
          <h4><div>Burrito</div><div class="price">$13.00</div></h4>
          <p>Served with guacamole</p>
        </div>
        <div class="ct-mini-menu-item">
          <div class="ct-mini-menu-top"><h5>Chicken Sandwich</h5><span class="custom-primary">$<!-- -->15</span></div>
          <div class="ct-mini-menu-bottom"><p>Served on a roll</p></div>
        </div>
        <div class="menu-column-left">
          <p><span class="menu-item">Tomato Salad<span> 12</span></span><br>Tomatoes and basil</p>
        </div>
    """, menu_context=True)

    assert page.menu_items == [
        ("Burrito", "Served with guacamole"), ("Chicken Sandwich", "Served on a roll"),
        ("Tomato Salad", "Tomatoes and basil"),
    ]
    assert page.menu_prices == {"chicken sandwich": (MenuPrice(1500),), "tomato salad": (MenuPrice(1200),)}
